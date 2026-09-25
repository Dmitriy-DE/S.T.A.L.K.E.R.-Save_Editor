"""Capability-bound item detail panel for the canonical editor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from editor.capabilities import FormatCapabilities
from editor.catalog import UpgradeCatalog
from editor.equipment import category_label
from editor.i18n import tr
from editor.official_names import official_name
from editor.s2_names import s2_readable_name
from save_format import InventoryItem

from .formatting import count_ru
from .style_components import action_button, panel, section_header, status_chip
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import technical_details

_DETAIL_IMAGE_SIZE = QSize(355, 80)
_PLACEMENT_LABELS = {"belt": tr("Пояс"), "ruck": tr("Рюкзак")}
_SOURCE_LABELS = {
    "actor_inventory": tr("инвентарь игрока"),
    "grid": tr("инвентарь"),
    "equipped": tr("экипировка"),
}


def _detail_pixmap(icon: QIcon) -> QPixmap:
    """Scale resolver artwork into the detail slot without distorting it."""

    source = icon.pixmap(QSize(420, 160))
    if source.isNull():
        return QPixmap()
    return source.scaled(
        _DETAIL_IMAGE_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _placement_text(placement_type: str | None, slot: int | None) -> str:
    if placement_type == "slot":
        return tr("Слот {0}", slot) if slot is not None else tr("Слот")
    return _PLACEMENT_LABELS.get(str(placement_type), "—")


class ItemDetailView(QWidget):
    """Render one item and expose only capability-approved draft controls."""

    count_stage_requested = Signal(int, int)
    durability_stage_requested = Signal(int, float)
    placement_stage_requested = Signal(int, str, object)
    upgrades_stage_requested = Signal(int, object)
    remove_requested = Signal(int)
    reset_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("itemDetailView")
        self._item: InventoryItem | None = None
        self._display_name: str | None = None
        self._category_key: str | None = None
        self._capabilities: FormatCapabilities | None = None
        self._upgrade_catalog: UpgradeCatalog | None = None
        self._staged_counts: Mapping[int, int] = {}
        self._staged_durability: Mapping[int, float] = {}
        self._staged_placements: Mapping[int, tuple[str, int | None]] = {}
        self._staged_upgrades: Mapping[int, tuple[str, ...]] = {}
        self._removed_handles: Mapping[int, bool] = {}
        self._item_icon: QIcon | None = None
        self._pixmap_cache: dict[int, QPixmap] = {}
        self._operation_detail_text = ""
        self._details_dialog: TechnicalDetailsDialog | None = None
        self._upgrades_writable = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 2)
        root.setSpacing(4)
        self.detail_scroll = QScrollArea(self)
        self.detail_scroll.setObjectName("itemDetailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.detail_content = QWidget(self.detail_scroll)
        self.detail_content.setObjectName("itemDetailContent")
        body = QVBoxLayout(self.detail_content)
        body.setContentsMargins(0, 0, 5, 4)
        body.setSpacing(4)
        self.status_chip = status_chip(tr("ТОЛЬКО ЧТЕНИЕ"), self.detail_content, tone="neutral")
        detail_header = section_header(tr("ПРЕДМЕТ"), parent=self.detail_content)
        detail_header.setObjectName("detailHeader")
        detail_header.setFixedHeight(40)
        detail_header_layout = detail_header.layout()
        if detail_header_layout is None:
            raise RuntimeError("item detail header has no layout")
        detail_header_layout.addWidget(self.status_chip)
        body.addWidget(detail_header)
        self.name_label = QLabel(tr("Предмет не выбран"), self.detail_content)
        self.name_label.setObjectName("detailItemName")
        self.name_label.setWordWrap(True)
        body.addWidget(self.name_label)
        self.type_label = QLabel(tr("Выбери строку инвентаря"), self.detail_content)
        self.type_label.setObjectName("detailItemType")
        body.addWidget(self.type_label)
        self.image_label = QLabel("", self.detail_content)
        self.image_label.setObjectName("detailItemImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setFixedHeight(86)
        body.addWidget(self.image_label)
        body.addSpacing(8)

        self.detail_tabs: list[QPushButton] = []
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        for index, label in enumerate((tr("ОСНОВНОЕ"), tr("МОДИФИКАЦИИ"), tr("ХАРАКТЕРИСТИКИ"))):
            button = QPushButton(label, self.detail_content)
            button.setObjectName("detailTab")
            button.setToolTip(label.capitalize())
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, selected=index: self._select_detail_tab(selected))
            tabs.addWidget(button, 1)
            self.detail_tabs.append(button)
        body.addLayout(tabs)

        self.detail_pages = QStackedWidget(self.detail_content)
        self.detail_pages.setObjectName("detailPages")
        body.addWidget(self.detail_pages)

        # Page 0: the values this save can change for the selected item.
        form_panel = panel(self.detail_pages, object_name="detailFields")
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.setSpacing(6)
        self.detail_form = QFormLayout()
        self.detail_form.setSpacing(8)
        self.count_spin = QSpinBox(form_panel)
        self.count_spin.setRange(1, 1_000_000)
        self.count_spin.setKeyboardTracking(False)
        self.count_spin.valueChanged.connect(lambda _value: self._emit_count())
        self.detail_form.addRow(tr("Количество"), self.count_spin)
        self.condition_spin = QDoubleSpinBox(form_panel)
        self.condition_spin.setRange(0.0, 100.0)
        self.condition_spin.setDecimals(1)
        self.condition_spin.setSuffix(" %")
        self.condition_spin.setKeyboardTracking(False)
        self.condition_spin.valueChanged.connect(lambda _value: self._emit_condition())
        self.detail_form.addRow(tr("Состояние"), self.condition_spin)
        self.placement_combo = QComboBox(form_panel)
        self.placement_combo.currentIndexChanged.connect(lambda _index: self._emit_placement())
        self.detail_form.addRow(tr("Размещение"), self.placement_combo)
        form_layout.addLayout(self.detail_form)
        self.fields_note = QLabel("", form_panel)
        self.fields_note.setObjectName("detailFieldsNote")
        self.fields_note.setWordWrap(True)
        form_layout.addWidget(self.fields_note)
        self.detail_pages.addWidget(form_panel)

        # Page 1: installed modules / upgrades, editable only where proven.
        upgrades_page = QWidget(self.detail_pages)
        upgrades_layout = QVBoxLayout(upgrades_page)
        upgrades_layout.setContentsMargins(0, 6, 0, 0)
        upgrades_layout.setSpacing(6)
        self.upgrade_heading = QLabel(tr("УСТАНОВЛЕННЫЕ МОДИФИКАЦИИ"), upgrades_page)
        self.upgrade_heading.setObjectName("detailUpgradesHeading")
        upgrades_layout.addWidget(self.upgrade_heading)
        self.upgrade_list = QListWidget(upgrades_page)
        self.upgrade_list.setObjectName("detailUpgradeList")
        self.upgrade_list.setMinimumHeight(118)
        upgrades_layout.addWidget(self.upgrade_list, 1)
        self.upgrade_status = QLabel("", upgrades_page)
        self.upgrade_status.setObjectName("detailUpgradeStatus")
        self.upgrade_status.setWordWrap(True)
        upgrades_layout.addWidget(self.upgrade_status)
        self.upgrade_apply_button = action_button(tr("ПРИМЕНИТЬ МОДИФИКАЦИИ"), upgrades_page)
        self.upgrade_apply_button.setObjectName("detailUpgradeApply")
        self.upgrade_apply_button.clicked.connect(self._emit_upgrades)
        upgrades_layout.addWidget(self.upgrade_apply_button)
        self.detail_pages.addWidget(upgrades_page)

        # Page 2: read-only characteristics and the technical escape hatch.
        facts_page = QWidget(self.detail_pages)
        facts_layout = QVBoxLayout(facts_page)
        facts_layout.setContentsMargins(0, 6, 0, 0)
        facts_layout.setSpacing(6)
        self.description_label = QLabel(tr("Данные взяты из открытого сохранения."), facts_page)
        self.description_label.setObjectName("detailDescription")
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        facts_layout.addWidget(self.description_label)
        self.details_button = action_button(tr("ТЕХНИЧЕСКИЕ ДЕТАЛИ"), facts_page)
        self.details_button.setObjectName("itemTechnicalDetailsButton")
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self._show_technical_details)
        facts_layout.addWidget(self.details_button)
        facts_layout.addStretch(1)
        self.detail_pages.addWidget(facts_page)

        self.module_status = QLabel("", self.detail_content)
        self.module_status.setObjectName("detailModuleStatus")
        self.module_status.setWordWrap(True)
        body.addWidget(self.module_status)
        body.addStretch(1)
        self.detail_scroll.setWidget(self.detail_content)
        root.addWidget(self.detail_scroll, 1)

        self.save_button = action_button(tr("СОХРАНИТЬ 0 ИЗМЕНЕНИЙ"), self, kind="primary", object_name="primaryActionButton")
        self.save_button.setMinimumHeight(42)
        self.save_button.setFixedHeight(42)
        self.save_button.setEnabled(False)
        root.addWidget(self.save_button)
        root.addSpacing(6)
        actions = QHBoxLayout()
        self.reset_button = action_button(tr("СБРОСИТЬ"), self)
        self.reset_button.setFixedHeight(38)
        self.reset_button.setEnabled(False)
        self.reset_button.setToolTip(tr("Отменить черновые изменения выбранного предмета"))
        self.reset_button.clicked.connect(self._emit_reset)
        actions.addWidget(self.reset_button)
        self.remove_button = action_button(tr("УДАЛИТЬ ПРЕДМЕТ"), self, kind="danger")
        self.remove_button.setFixedHeight(38)
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self._emit_remove)
        actions.addWidget(self.remove_button)
        root.addLayout(actions)
        self._select_detail_tab(0)

    def set_compact(self, compact: bool) -> None:
        labels = (
            (tr("ОСНОВНОЕ"), tr("МОДИФ."), tr("ХАРАКТ."))
            if compact
            else (tr("ОСНОВНОЕ"), tr("МОДИФИКАЦИИ"), tr("ХАРАКТЕРИСТИКИ"))
        )
        for button, label in zip(self.detail_tabs, labels, strict=True):
            button.setText(label)

    def _select_detail_tab(self, index: int) -> None:
        for button_index, button in enumerate(self.detail_tabs):
            button.setChecked(button_index == index)
        self.detail_pages.setCurrentIndex(index)

    def set_item(
        self,
        item: InventoryItem | None,
        capabilities: FormatCapabilities | None,
        *,
        upgrade_catalog: UpgradeCatalog | None = None,
        staged_counts: Mapping[int, int] | None = None,
        staged_durability: Mapping[int, float] | None = None,
        removed_handles: Mapping[int, bool] | None = None,
        staged_placements: Mapping[int, tuple[str, int | None]] | None = None,
        staged_upgrades: Mapping[int, tuple[str, ...]] | None = None,
        display_name: str | None = None,
        category_key: str | None = None,
        group_size: int = 1,
    ) -> None:
        self._group_size = max(1, int(group_size))
        self._item = item
        self._capabilities = capabilities
        self._upgrade_catalog = upgrade_catalog
        self._staged_counts = staged_counts or {}
        self._staged_durability = staged_durability or {}
        self._removed_handles = removed_handles or {}
        self._staged_placements = staged_placements or {}
        self._staged_upgrades = staged_upgrades or {}
        self._display_name = display_name
        self._category_key = category_key
        self._render()

    def set_item_icon(self, icon: QIcon | None) -> None:
        self._item_icon = icon
        self._render_icon()

    def set_operation_details(self, value: str) -> None:
        self._operation_detail_text = str(value or "")
        self.details_button.setVisible(bool(self._item or self._operation_detail_text))

    def set_change_count(self, count: int) -> None:
        self.save_button.setText(
            tr("СОХРАНИТЬ {0}", count_ru(count, 'ИЗМЕНЕНИЕ', 'ИЗМЕНЕНИЯ', 'ИЗМЕНЕНИЙ'))
        )
        self.save_button.setEnabled(count > 0)

    def _render_icon(self) -> None:
        icon = self._item_icon
        if self._item is None or icon is None or icon.isNull():
            self.image_label.clear()
            return
        key = icon.cacheKey()
        pixmap = self._pixmap_cache.get(key)
        if pixmap is None:
            pixmap = _detail_pixmap(icon)
            if len(self._pixmap_cache) > 64:
                self._pixmap_cache.clear()
            self._pixmap_cache[key] = pixmap
        self.image_label.setPixmap(pixmap)

    def _render(self) -> None:
        item = self._item
        caps = self._capabilities
        if item is None:
            self.name_label.setText(tr("Предмет не выбран"))
            self.type_label.setText(tr("Выбери строку инвентаря"))
            self.description_label.setText(tr("Данные взяты из открытого сохранения."))
            self._set_status(tr("ТОЛЬКО ЧТЕНИЕ"), "neutral")
            for widget in (self.count_spin, self.condition_spin, self.placement_combo):
                self.detail_form.setRowVisible(widget, False)
            self.fields_note.setText("")
            self.reset_button.setEnabled(False)
            self.remove_button.setVisible(False)
            self.remove_button.setEnabled(False)
            self.upgrade_list.clear()
            self.upgrade_apply_button.setVisible(False)
            self.upgrade_status.setText("")
            self.module_status.setText("")
            self.details_button.setVisible(bool(self._operation_detail_text))
            self.image_label.clear()
            return

        self.name_label.setText(self._display_name or item.display_name or tr("Неизвестный предмет"))
        self.details_button.setVisible(True)
        self.type_label.setText(
            category_label(self._category_key) if self._category_key else item.category
        )

        writable_stack = bool(caps and caps.edit_stacks and item.editable_count)
        writable_condition = bool(
            caps and caps.edit_durability and item.condition_editable and item.condition is not None
        )
        placement_writable = bool(
            caps and caps.edit_placement and item.placement_editable and item.placement_type is not None
        )
        self._upgrades_writable = bool(
            caps
            and caps.edit_upgrades
            and item.upgrades is not None
            and item.upgrades_editable
            and self._upgrade_catalog is not None
        )
        can_remove = bool(caps and caps.remove_items and item.remove_editable)
        grouped = getattr(self, "_group_size", 1) > 1
        if grouped:
            # A folded row stands for several objects; a change must name one.
            writable_stack = placement_writable = can_remove = False
        if item.handle in self._removed_handles:
            # Editing an item that is staged for removal would make the plan
            # contradict itself; only "ВЕРНУТЬ ПРЕДМЕТ" stays available.
            writable_stack = writable_condition = placement_writable = False
            self._upgrades_writable = False
        supports = []
        if caps is not None:
            for writable, name in (
                (writable_stack, "edit_stacks"),
                (writable_condition, "edit_durability"),
                (placement_writable, "edit_placement"),
                (self._upgrades_writable, "edit_upgrades"),
                (can_remove, "remove_items"),
            ):
                if writable:
                    supports.append(caps.support(name))
        if not supports:
            self._set_status(tr("ТОЛЬКО ЧТЕНИЕ"), "neutral")
        elif any(support.maturity == "experimental" for support in supports):
            self._set_status(tr("ЭКСПЕРИМЕНТАЛЬНО"), "warning")
        else:
            self._set_status(tr("МОЖНО ИЗМЕНИТЬ"), "success")

        # Rows the save does not have are hidden instead of showing "0 %".
        has_count = item.count is not None
        count = self._staged_counts.get(item.handle, item.count or 1)
        self.count_spin.blockSignals(True)
        self.count_spin.setMaximum(max(1, item.count_max, count))
        self.count_spin.setValue(count)
        self.count_spin.blockSignals(False)
        self.count_spin.setEnabled(writable_stack)
        self.detail_form.setRowVisible(self.count_spin, has_count)

        has_condition = item.condition is not None
        condition = self._staged_durability.get(item.handle, item.condition or 0.0)
        self.condition_spin.blockSignals(True)
        self.condition_spin.setValue(condition * 100.0)
        self.condition_spin.blockSignals(False)
        self.condition_spin.setEnabled(writable_condition)
        self.detail_form.setRowVisible(self.condition_spin, has_condition)

        has_placement = item.placement_type is not None
        staged_place = self._staged_placements.get(item.handle)
        effective_placement = staged_place or (
            item.placement_type,
            item.placement_slot if item.placement_type == "slot" else None,
        )
        self.placement_combo.blockSignals(True)
        self.placement_combo.clear()
        # Exactly the values the X-Ray place codec accepts.
        self.placement_combo.addItem(tr("Рюкзак"), ("ruck", None))
        self.placement_combo.addItem(tr("Пояс"), ("belt", None))
        for slot in range(1, 14):
            self.placement_combo.addItem(tr("Слот {0}", slot), ("slot", slot))
        for index in range(self.placement_combo.count()):
            if tuple(self.placement_combo.itemData(index)) == tuple(effective_placement):
                self.placement_combo.setCurrentIndex(index)
                break
        self.placement_combo.blockSignals(False)
        self.placement_combo.setEnabled(placement_writable)
        self.detail_form.setRowVisible(self.placement_combo, has_placement)

        if grouped:
            self.fields_note.setText(
                tr("Здесь {0} одинаковых предметов. Чтобы изменить или удалить один, выключи «Объединять одинаковые».", self._group_size)
            )
        elif item.handle in self._removed_handles:
            self.fields_note.setText(tr("Предмет будет удалён при сохранении."))
        elif not (has_count or has_condition or has_placement):
            self.fields_note.setText(tr("Для этого предмета в сохранении нет изменяемых полей."))
        elif not (writable_stack or writable_condition or placement_writable):
            self.fields_note.setText(tr("Эти значения доступны только для просмотра."))
        else:
            self.fields_note.setText("")

        self._render_upgrades(item)
        weight = "—" if item.total_weight is None else tr("{0:.1f} кг", item.total_weight)
        source = _SOURCE_LABELS.get(str(item.observation_source or ""), tr("открытое сохранение"))
        facts = [
            tr("Тип: {0}", self.type_label.text()),
            tr("Вес: {0}", weight),
        ]
        if item.unit_weight is not None and (item.count or 1) > 1:
            facts.append(tr("Вес одного: {0:.2f} кг", item.unit_weight))
        if item.condition is not None:
            facts.append(tr("Состояние: {0:.0f}%", item.condition * 100.0))
        if item.modules:
            facts.append(
                tr("Установлено: {0}", ", ".join(self._module_name(value) for value in item.modules))
            )
        effects = self._upgrade_effects(item.upgrades or ())
        if effects:
            facts.append(tr("Улучшения:"))
            facts.extend(f"  • {line}" for line in effects)
        facts.append(tr("Источник: {0}", source))
        if has_placement:
            facts.append(
                tr("Размещение: ")
                + _placement_text(item.placement_type, item.placement_slot)
            )
        if grouped:
            facts.append(tr("Одинаковых предметов: {0}", self._group_size))
        elif item.count is not None:
            facts.append(tr("Количество в сохранении: {0}", item.count))
        self.description_label.setText("\n".join(facts))
        self.reset_button.setEnabled(
            any(
                item.handle in mapping
                for mapping in (
                    self._staged_counts,
                    self._staged_durability,
                    self._removed_handles,
                    self._staged_placements,
                    self._staged_upgrades,
                )
            )
        )
        # Unsupported formats must not present a destructive affordance that
        # can never succeed; the S2 add/remove surface is omitted entirely.
        self.remove_button.setVisible(can_remove)
        self.remove_button.setEnabled(can_remove)
        self.remove_button.setText(
            tr("ВЕРНУТЬ ПРЕДМЕТ") if item.handle in self._removed_handles else tr("УДАЛИТЬ ПРЕДМЕТ")
        )
        self._render_icon()

    def _module_name(self, sid: str) -> str:
        if getattr(self, "_stalker2", False):
            return s2_readable_name(sid) or sid
        return self._upgrade_label(sid, 0)

    def _upgrade_effects(self, upgrades: tuple[str, ...]) -> list[str]:
        """Group installed upgrades by effect: «Пси-защита · ур. 2, ур. 3»."""

        grouped: dict[str, list[str]] = {}
        for index, key in enumerate(upgrades, start=1):
            label = self._upgrade_label(str(key), index)
            name, _sep, level = label.partition(" · ")
            grouped.setdefault(name, [])
            if level:
                grouped[name].append(level)
        lines = []
        for name, levels in grouped.items():
            unique = list(dict.fromkeys(levels))
            text = f"{name} · {', '.join(unique)}" if unique else name
            if len(levels) > len(unique):
                text += f" ×{len(levels)}"
            lines.append(text)
        return lines

    def set_release(self, release_id: str) -> None:
        self._release_id = str(release_id or "")
        self._stalker2 = self._release_id.startswith("stalker2")

    def _upgrade_label(self, key: str, index: int) -> str:
        """Readable name, or a neutral placeholder: raw IDs live in details."""

        official = official_name(getattr(self, "_release_id", None), "upgrades", key)
        if official:
            return official
        catalog = self._upgrade_catalog
        definition = catalog.resolve(key) if catalog is not None else None
        name = definition.display_name if definition is not None else None
        # Generated catalogs can contain localization tokens rather than
        # translated labels; those are not readable names either.
        if name and not name.casefold().startswith("st_"):
            return name
        if getattr(self, "_stalker2", False):
            return s2_readable_name(key) or key
        return tr("Улучшение {0}", index)

    def _render_upgrades(self, item: InventoryItem) -> None:
        self.upgrade_list.blockSignals(True)
        self.upgrade_list.clear()
        installed = tuple(item.upgrades or item.modules or ())
        effective = self._staged_upgrades.get(item.handle, installed)
        catalog = self._upgrade_catalog
        if self._upgrades_writable and catalog is not None:
            keys = list(installed)
            keys.extend(
                definition.key
                for definition in catalog.for_item(item.type_key)
                if definition.key not in keys
            )
            for index, key in enumerate(keys, start=1):
                entry = QListWidgetItem(self._upgrade_label(key, index))
                entry.setData(Qt.ItemDataRole.UserRole, key)
                entry.setSizeHint(QSize(0, 26))
                entry.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                entry.setCheckState(
                    Qt.CheckState.Checked if key in effective else Qt.CheckState.Unchecked
                )
                self.upgrade_list.addItem(entry)
            self.upgrade_apply_button.setVisible(bool(keys))
            self.upgrade_heading.setText(tr("МОДИФИКАЦИИ · УСТАНОВЛЕНО {0}", len(effective)))
            self.upgrade_status.setText(
                tr("Отметь модификации и нажми «Применить». Запись — экспериментальная, перед сохранением создаётся резервная копия.")
                if keys
                else tr("Для этого предмета в каталоге нет модификаций.")
            )
        else:
            for index, value in enumerate(effective, start=1):
                label = self._upgrade_label(str(value), index)
                row = QListWidgetItem(label)
                row.setSizeHint(QSize(0, 26))
                row.setData(Qt.ItemDataRole.AccessibleTextRole, label)
                self.upgrade_list.addItem(row)
            self.upgrade_apply_button.setVisible(False)
            self.upgrade_heading.setText(tr("УСТАНОВЛЕННЫЕ МОДИФИКАЦИИ"))
            self.upgrade_status.setText(
                tr("Модули и улучшения доступны только для просмотра.")
                if effective
                else tr("Данные о модификациях недоступны.")
            )
        self.upgrade_list.blockSignals(False)

    _STATUS_TOOLTIPS: ClassVar[dict[str, str]] = {
        "neutral": "Это поле распознано, но запись в него не подтверждена на реальных сохранениях.",
        "warning": (
            "Запись проверена на части сохранений. Перед сохранением создаётся "
            "резервная копия, а результат перечитывается и сверяется."
        ),
        "success": "Изменение проверено на реальных сохранениях этой игры.",
    }

    def _set_status(self, text: str, tone: str) -> None:
        self.status_chip.setText(text)
        tip = self._STATUS_TOOLTIPS.get(tone)
        self.status_chip.setToolTip(tr(tip) if tip else "")
        self.status_chip.setProperty("tone", tone)
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)

    def _show_technical_details(self) -> None:
        item = self._item
        if item is None and not self._operation_detail_text:
            return
        lines: list[str] = []
        if item is not None:
            lines.extend(
                (
                    tr("Идентификатор предмета: {0}", item.handle_hex),
                    tr("Ключ типа: {0}", item.type_key),
                    tr("Категория в сохранении: {0}", item.category),
                    tr("Источник данных: {0}", item.observation_source or tr("не определено")),
                )
            )
            if item.modules:
                lines.append(tr("Идентификаторы модулей: {0}", ', '.join(item.modules)))
            if item.upgrades:
                lines.append(tr("Идентификаторы модификаций: {0}", ', '.join(item.upgrades)))
        if self._operation_detail_text:
            lines.append(self._operation_detail_text)
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(
            technical_details("\n".join(lines)), self
        )
        self._details_dialog.open()

    def _emit_count(self) -> None:
        if self._item is not None:
            self.count_stage_requested.emit(self._item.handle, self.count_spin.value())

    def _emit_condition(self) -> None:
        if self._item is not None:
            self.durability_stage_requested.emit(self._item.handle, self.condition_spin.value() / 100.0)

    def _emit_placement(self) -> None:
        if self._item is not None:
            value = self.placement_combo.currentData()
            if isinstance(value, (tuple, list)) and len(value) == 2:
                self.placement_stage_requested.emit(self._item.handle, str(value[0]), value[1])

    def _emit_upgrades(self) -> None:
        if self._item is None or not self._upgrades_writable:
            return
        values = tuple(
            str(self.upgrade_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.upgrade_list.count())
            if self.upgrade_list.item(index).checkState() == Qt.CheckState.Checked
        )
        self.upgrades_stage_requested.emit(self._item.handle, values)

    def _emit_reset(self) -> None:
        if self._item is not None:
            self.reset_requested.emit(self._item.handle)

    def _emit_remove(self) -> None:
        if self._item is not None:
            self.remove_requested.emit(self._item.handle)


__all__ = ["ItemDetailView"]
