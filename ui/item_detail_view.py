"""Capability-bound item detail panel for the canonical editor."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QRect, QSize, Qt, Signal
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
    QVBoxLayout,
    QWidget,
)

from editor.capabilities import FormatCapabilities
from editor.catalog import UpgradeCatalog
from save_format import InventoryItem

from .style_components import action_button, panel, section_header, status_chip
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import technical_details

_DETAIL_TYPE_LABELS = {
    "mp_wpn_ak74": "Штурмовая винтовка",
    "mp_wpn_toz34": "Дробовик",
    "cs_heavy_outfit": "Броня",
    "helm_respirator": "Шлем",
    "detector_advanced": "Детектор",
    "zat_b33_safe_container": "Контейнер",
}


def _wide_detail_pixmap(icon: QIcon) -> QPixmap:
    """Place resolver artwork into the broad weapon-art slot used by the reference."""

    source = icon.pixmap(QSize(380, 86)).toImage()
    if source.isNull():
        return QPixmap()
    left, top, right, bottom = source.width(), source.height(), -1, -1
    for alpha_threshold in (128, 8):
        for y in range(source.height()):
            for x in range(source.width()):
                if source.pixelColor(x, y).alpha() > alpha_threshold:
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)
        if right >= left and bottom >= top:
            break
    if right < left or bottom < top:
        return QPixmap()
    cropped = source.copy(QRect(left, top, right - left + 1, bottom - top + 1))
    return QPixmap.fromImage(
        cropped.scaled(
            QSize(355, 80),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


class ItemDetailView(QWidget):
    """Render one item and expose only capability-approved draft controls."""

    count_stage_requested = Signal(int, int)
    durability_stage_requested = Signal(int, float)
    placement_stage_requested = Signal(int, str, object)
    remove_requested = Signal(int)
    reset_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("itemDetailView")
        self._item: InventoryItem | None = None
        self._capabilities: FormatCapabilities | None = None
        self._upgrade_catalog: UpgradeCatalog | None = None
        self._staged_counts: Mapping[int, int] = {}
        self._staged_durability: Mapping[int, float] = {}
        self._removed_handles: Mapping[int, bool] = {}
        self._item_icon: QIcon | None = None
        self._operation_detail_text = ""
        self._details_dialog: TechnicalDetailsDialog | None = None
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
        self.status_chip = status_chip("ТОЛЬКО ПРОСМОТР", self.detail_content, tone="neutral")
        detail_header = section_header("РЕДАКТИРОВАНИЕ ПРЕДМЕТА", parent=self.detail_content)
        detail_header.setObjectName("detailHeader")
        detail_header.setFixedHeight(40)
        detail_header_layout = detail_header.layout()
        if detail_header_layout is None:
            raise RuntimeError("item detail header has no layout")
        detail_header_layout.addWidget(self.status_chip)
        body.addWidget(detail_header)
        self.name_label = QLabel("Предмет не выбран", self.detail_content)
        self.name_label.setObjectName("detailItemName")
        body.addWidget(self.name_label)
        self.type_label = QLabel("Выбери строку инвентаря", self.detail_content)
        self.type_label.setObjectName("detailItemType")
        body.addWidget(self.type_label)
        self.image_label = QLabel("—", self.detail_content)
        self.image_label.setObjectName("detailItemImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.image_label.setFixedHeight(86)
        body.addWidget(self.image_label)
        self.description_label = QLabel("Данные взяты из открытого сохранения.", self.detail_content)
        self.description_label.setObjectName("detailDescription")
        self.description_label.setWordWrap(True)
        body.addWidget(self.description_label)
        body.addSpacing(14)

        self.detail_tabs: list[QPushButton] = []
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        for index, label in enumerate(("ОСНОВНОЕ", "МОДИФИКАЦИИ", "ХАРАКТЕРИСТИКИ")):
            button = QPushButton(label, self.detail_content)
            button.setObjectName("detailTab")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, selected=index: self._select_detail_tab(selected))
            tabs.addWidget(button, 1)
            self.detail_tabs.append(button)
        self.detail_tabs[0].setChecked(True)
        body.addLayout(tabs)

        form_panel = panel(self.detail_content, object_name="detailFields")
        form = QFormLayout(form_panel)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(8)
        self.count_spin = QSpinBox(form_panel)
        self.count_spin.setRange(1, 1_000_000)
        self.count_spin.valueChanged.connect(lambda _value: self._emit_count())
        form.addRow("Количество", self.count_spin)

        self.condition_spin = QDoubleSpinBox(form_panel)
        self.condition_spin.setRange(0.0, 100.0)
        self.condition_spin.setDecimals(1)
        self.condition_spin.setSuffix(" %")
        self.condition_spin.valueChanged.connect(lambda _value: self._emit_condition())
        form.addRow("Состояние", self.condition_spin)

        self.placement_combo = QComboBox(form_panel)
        self.placement_combo.addItem("Инвентарь", ("inventory", None))
        self.placement_combo.addItem("Пояс", ("belt", None))
        self.placement_combo.addItem("Рюкзак", ("ruck", None))
        self.placement_combo.currentIndexChanged.connect(lambda _index: self._emit_placement())
        form.addRow("Размещение", self.placement_combo)
        body.addWidget(form_panel)

        body.addSpacing(14)
        self.upgrade_heading = QLabel(
            "УСТАНОВЛЕННЫЕ МОДУЛИ / УЛУЧШЕНИЯ",
            self.detail_content,
        )
        self.upgrade_heading.setObjectName("detailUpgradesHeading")
        body.addWidget(self.upgrade_heading)
        self.upgrade_list = QListWidget(self.detail_content)
        self.upgrade_list.setObjectName("detailUpgradeList")
        self.upgrade_list.setMaximumHeight(118)
        body.addWidget(self.upgrade_list)
        self.module_status = QLabel("—", self.detail_content)
        self.module_status.setObjectName("detailModuleStatus")
        self.module_status.setWordWrap(True)
        body.addWidget(self.module_status)
        self.details_button = action_button("ТЕХНИЧЕСКИЕ ДЕТАЛИ", self.detail_content)
        self.details_button.setObjectName("itemTechnicalDetailsButton")
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self._show_technical_details)
        body.addWidget(self.details_button)
        feature_row = QHBoxLayout()
        feature_row.setSpacing(6)
        self.verified_feature_chip = status_chip("ПРОВЕРЕНО", self.detail_content, tone="success")
        self.read_only_feature_chip = status_chip("ТОЛЬКО ПРОСМОТР", self.detail_content, tone="neutral")
        self.feature_help = QLabel("?", self.detail_content)
        self.feature_help.setObjectName("detailFeatureHelp")
        feature_row.addWidget(self.verified_feature_chip)
        feature_row.addWidget(self.read_only_feature_chip)
        feature_row.addWidget(self.feature_help)
        feature_row.addStretch(1)
        body.addLayout(feature_row)
        body.addStretch(1)
        self.detail_scroll.setWidget(self.detail_content)
        root.addWidget(self.detail_scroll, 1)

        self.save_button = action_button("СОХРАНИТЬ 0 ИЗМЕНЕНИЙ", self, kind="primary", object_name="primaryActionButton")
        self.save_button.setMinimumHeight(42)
        self.save_button.setFixedHeight(42)
        self.save_button.setEnabled(False)
        root.addWidget(self.save_button)
        root.addSpacing(6)
        actions = QHBoxLayout()
        self.reset_button = action_button("СБРОСИТЬ", self)
        self.reset_button.setFixedHeight(38)
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(self._emit_reset)
        actions.addWidget(self.reset_button)
        self.remove_button = action_button("УДАЛИТЬ ПРЕДМЕТ", self, kind="danger")
        self.remove_button.setFixedHeight(38)
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self._emit_remove)
        actions.addWidget(self.remove_button)
        root.addLayout(actions)

    def _select_detail_tab(self, index: int) -> None:
        for button_index, button in enumerate(self.detail_tabs):
            button.setChecked(button_index == index)
        if index == 1 and self._item is not None:
            self.module_status.setText(
                "Установленные модули и улучшения доступны только для просмотра."
            )
        elif index == 2 and self._item is not None:
            self.module_status.setText(
                "Характеристики показываются по открытому сохранению."
            )
        elif self._item is not None:
            self.module_status.setText(
                "Модули и улучшения доступны только для просмотра."
                if self._item.upgrades or self._item.modules
                else "Данные о модификациях недоступны."
            )

    def set_item(
        self,
        item: InventoryItem | None,
        capabilities: FormatCapabilities | None,
        *,
        upgrade_catalog: UpgradeCatalog | None = None,
        staged_counts: Mapping[int, int] | None = None,
        staged_durability: Mapping[int, float] | None = None,
        removed_handles: Mapping[int, bool] | None = None,
    ) -> None:
        self._item = item
        self._capabilities = capabilities
        self._upgrade_catalog = upgrade_catalog
        self._staged_counts = staged_counts or {}
        self._staged_durability = staged_durability or {}
        self._removed_handles = removed_handles or {}
        self._render()

    def set_item_icon(self, icon: QIcon | None) -> None:
        self._item_icon = icon
        self._render()

    def set_operation_details(self, value: str) -> None:
        self._operation_detail_text = str(value or "")
        self.details_button.setVisible(bool(self._item or self._operation_detail_text))

    def set_change_count(self, count: int) -> None:
        self.save_button.setText(f"СОХРАНИТЬ {count} ИЗМЕНЕНИЙ")
        self.save_button.setEnabled(count > 0)

    def _render(self) -> None:
        item = self._item
        caps = self._capabilities
        if item is None:
            self.name_label.setText("Предмет не выбран")
            self.type_label.setText("Выбери строку инвентаря")
            self.description_label.setText("Данные взяты из открытого сохранения.")
            self.status_chip.setText("ТОЛЬКО ПРОСМОТР")
            self.count_spin.setEnabled(False)
            self.condition_spin.setEnabled(False)
            self.placement_combo.setEnabled(False)
            self.reset_button.setEnabled(False)
            self.remove_button.setVisible(False)
            self.remove_button.setEnabled(False)
            self.upgrade_list.clear()
            self.module_status.setText("—")
            self.details_button.setVisible(bool(self._operation_detail_text))
            self.image_label.clear()
            self.image_label.setText("—")
            return

        label = item.display_name or "Неизвестный объект"
        self.name_label.setText(label)
        self.details_button.setVisible(True)
        type_label = _DETAIL_TYPE_LABELS.get(item.type_key, item.category)
        self.type_label.setText(type_label)
        weight = "—" if item.total_weight is None else f"{item.total_weight:.1f} кг"
        source_labels = {
            "actor_inventory": "инвентарь игрока",
            "grid": "инвентарь",
            "equipped": "экипировка",
        }
        source = source_labels.get(str(item.observation_source or ""), "открытое сохранение")
        self.description_label.setText(f"Вес: {weight}\nИсточник: {source}")
        if self._item_icon is not None and not self._item_icon.isNull():
            self.image_label.setPixmap(_wide_detail_pixmap(self._item_icon))
            self.image_label.setText("")
        else:
            self.image_label.setText("—")

        stack_support = caps.support("edit_stacks") if caps is not None else None
        condition_support = caps.support("edit_durability") if caps is not None else None
        writable_stack = bool(caps and caps.edit_stacks and item.editable_count)
        writable_condition = bool(caps and caps.edit_durability and item.condition_editable and item.condition is not None)
        experimental = any(
            support is not None and support.maturity == "experimental"
            for support in (stack_support, condition_support)
        )
        self.status_chip.setText(
            "Экспериментальная функция"
            if experimental
            else "ПРОВЕРЕНО"
            if writable_stack or writable_condition
            else "ТОЛЬКО ПРОСМОТР"
        )
        self.status_chip.setProperty("tone", "warning" if experimental else "success" if writable_stack or writable_condition else "neutral")
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)

        count = self._staged_counts.get(item.handle, item.count or 1)
        self.count_spin.blockSignals(True)
        self.count_spin.setMaximum(max(1, item.count_max))
        self.count_spin.setValue(count)
        self.count_spin.blockSignals(False)
        self.count_spin.setEnabled(writable_stack)

        condition = self._staged_durability.get(item.handle, item.condition or 0.0)
        self.condition_spin.blockSignals(True)
        self.condition_spin.setValue(condition * 100.0)
        self.condition_spin.blockSignals(False)
        self.condition_spin.setEnabled(writable_condition)

        placement_writable = bool(caps and caps.edit_placement and item.placement_editable)
        self.placement_combo.blockSignals(True)
        self.placement_combo.clear()
        self.placement_combo.addItem("Инвентарь", ("inventory", None))
        self.placement_combo.addItem("Пояс", ("belt", None))
        self.placement_combo.addItem("Рюкзак", ("ruck", None))
        for slot in range(1, 14):
            self.placement_combo.addItem(f"Слот {slot}", ("slot", slot))
        effective_placement = (
            item.placement_type,
            item.placement_slot if item.placement_type == "slot" else None,
        )
        for index in range(self.placement_combo.count()):
            if self.placement_combo.itemData(index) == effective_placement:
                self.placement_combo.setCurrentIndex(index)
                break
        self.placement_combo.blockSignals(False)
        self.placement_combo.setEnabled(placement_writable)

        self.upgrade_list.clear()
        upgrade_values = item.upgrades or item.modules or ()
        for index, value in enumerate(upgrade_values, start=1):
            raw_key = str(value)
            definition = (
                self._upgrade_catalog.resolve(raw_key)
                if self._upgrade_catalog is not None
                else None
            )
            catalog_name = definition.display_name if definition is not None else None
            # Generated catalogs can contain localization tokens rather than
            # translated labels. Keep those identifiers out of the normal
            # screen; retain the exact key in the explicit detail dialog.
            label = (
                catalog_name
                if catalog_name and not catalog_name.casefold().startswith("st_")
                else f"Улучшение {index}"
            )
            row = QListWidgetItem(label)
            row.setSizeHint(QSize(0, 26))
            row.setData(Qt.ItemDataRole.AccessibleTextRole, label)
            self.upgrade_list.addItem(row)
        self.module_status.setText(
            "Модули и улучшения доступны только для просмотра."
            if item.upgrades or item.modules
            else "Данные о модификациях недоступны."
        )
        self.reset_button.setEnabled(
            item.handle in self._staged_counts
            or item.handle in self._staged_durability
            or item.handle in self._removed_handles
        )
        can_remove = bool(caps and caps.remove_items and item.remove_editable)
        # Unsupported formats must not present a destructive affordance that
        # can never succeed.  The capability remains truthful in the detail
        # state (count/durability controls are visibly read-only), while the
        # S2 add/remove surface is omitted entirely.
        self.remove_button.setVisible(can_remove)
        self.remove_button.setEnabled(can_remove)

    def _show_technical_details(self) -> None:
        item = self._item
        if item is None and not self._operation_detail_text:
            return
        lines: list[str] = []
        if item is not None:
            lines.extend(
                (
                    f"Идентификатор предмета: {item.handle_hex}",
                    f"Ключ типа: {item.type_key}",
                    f"Источник данных: {item.observation_source or 'не определено'}",
                )
            )
            if item.modules:
                lines.append(f"Идентификаторы модулей: {', '.join(item.modules)}")
            if item.upgrades:
                lines.append(f"Идентификаторы модификаций: {', '.join(item.upgrades)}")
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

    def _emit_reset(self) -> None:
        if self._item is not None:
            self.reset_requested.emit(self._item.handle)

    def _emit_remove(self) -> None:
        if self._item is not None:
            self.remove_requested.emit(self._item.handle)


__all__ = ["ItemDetailView"]
