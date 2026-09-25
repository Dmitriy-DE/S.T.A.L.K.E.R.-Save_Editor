"""Canonical three-column save editor surface."""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLocale, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from editor.capabilities import FormatCapabilities
from editor.catalog import ItemCatalog, UpgradeCatalog
from editor.equipment import EquipmentItem, equipment_items
from editor.i18n import tr
from editor.item_names import item_label
from editor.releases import is_xray_original_release
from save_format import InventoryItem

from .formatting import currency_suffix, human_money
from .inventory_model import InventoryTableModel
from .item_detail_view import ItemDetailView
from .style_components import action_button, panel, section_header, status_chip
from .xray_assets import XRayIconResolver, donor_resolver_for, fit_icon

# Loadout cards: most useful equipment first.  Knife, PDA and torch are
# always equipped in X-Ray and would crowd out armour and firearms.
_LOADOUT_PRIORITY = {"weapon": 0, "armor": 1, "helmet": 2, "device": 4}
_DEVICE_CARD_TITLES = {
    "detector": tr("ДЕТЕКТОР"),
    "binocular": tr("БИНОКЛЬ"),
    "nvg": tr("ПНВ"),
}
_LOW_PRIORITY_KEYS = ("wpn_knife", "device_pda", "device_torch", "wpn_binoc")
_CATEGORY_TABS = (
    (tr("ВСЕ"), "all"),
    (tr("ОРУЖИЕ"), "weapon"),
    (tr("БОЕПРИПАСЫ"), "ammo"),
    (tr("СНАРЯЖЕНИЕ"), "armor"),
    (tr("РАСХОДНИКИ"), "consumable"),
    (tr("АРТЕФАКТЫ"), "artifact"),
    (tr("КЛЮЧИ"), "quest"),
    (tr("ПРОЧЕЕ"), "other"),
)
_COMPACT_CATEGORY_LABELS = (tr("ВСЕ"), tr("ОРУЖ."), tr("ПАТР."), tr("СНАР."), tr("РАСХ."), tr("АРТ."), tr("КЛЮЧИ"), tr("ПРОЧ."))


class ConditionBarDelegate(QStyledItemDelegate):
    """Render the inventory condition as a compact label and durability meter."""

    def paint(self, painter: QPainter, option, index) -> None:
        raw_value = index.data(Qt.ItemDataRole.UserRole)
        display_text = str(index.data(Qt.ItemDataRole.DisplayRole) or "—")
        styled_option = QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)
        styled_option.text = ""
        super().paint(painter, styled_option, index)

        value: float | None
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = None
        if value is not None and not math.isfinite(value):
            value = None

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if value is None:
            text = display_text
            painter.setPen(
                QColor("#151713")
                if option.state & QStyle.StateFlag.State_Selected
                else QColor("#A29D90")
            )
            painter.drawText(
                option.rect.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )
            painter.restore()
            return

        value = min(1.0, max(0.0, value))
        text_color = (
            QColor("#151713")
            if option.state & QStyle.StateFlag.State_Selected
            else QColor("#D8D2BE")
        )
        painter.setPen(text_color)
        content = option.rect.adjusted(8, 0, -8, 0)
        label_width = 39
        painter.drawText(
            content.x(),
            content.y(),
            label_width,
            content.height(),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            f"{round(value * 100)}%",
        )
        bar_width = max(0, min(58, content.width() - label_width - 6))
        if bar_width:
            bar_height = 9
            bar = option.rect.adjusted(0, 0, 0, 0)
            bar_x = content.right() - bar_width + 1
            bar_y = bar.center().y() - bar_height // 2
            painter.setPen(QPen(QColor("#4B5048"), 1))
            painter.setBrush(QColor("#1D221E"))
            painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_height, 2, 2)
            fill_width = round((bar_width - 2) * value)
            fill_color = QColor(
                "#71C96A" if value >= 0.8 else "#E0B53D" if value >= 0.5 else "#D85A45"
            )
            if fill_width > 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill_color)
                painter.drawRoundedRect(
                    bar_x + 1,
                    bar_y + 1,
                    fill_width,
                    bar_height - 2,
                    1,
                    1,
                )
        painter.restore()
_SHELL_ICONS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "shell_icons"


class EditorView(QWidget):
    """A real editor layout; all mutation signals are intent-only."""

    back_requested = Signal()
    save_requested = Signal()
    character_requested = Signal()
    stack_stage_requested = Signal(int, int)
    durability_stage_requested = Signal(int, float)
    placement_stage_requested = Signal(int, str, object)
    remove_requested = Signal(int)
    reset_requested = Signal(int)
    upgrades_stage_requested = Signal(int, object)
    add_requested = Signal()
    repair_all_requested = Signal()
    discard_requested = Signal()
    compare_requested = Signal()
    money_stage_requested = Signal(int)
    money_clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("editorView")
        self.model = InventoryTableModel(self)
        self.model.set_name_provider(lambda item: item.display_name)
        self.selected_handle: int | None = None
        self._items: tuple[InventoryItem, ...] = ()
        self._capabilities: FormatCapabilities | None = None
        self._catalog: ItemCatalog | None = None
        self._upgrade_catalog: UpgradeCatalog | None = None
        self._icon_resolver = XRayIconResolver(None)
        self._staged_counts: Mapping[int, int] = {}
        self._staged_durability: Mapping[int, float] = {}
        self._removed_handles: Mapping[int, bool] = {}
        self._staged_placements: Mapping[int, tuple[str, int | None]] = {}
        self._staged_upgrades: Mapping[int, tuple[str, ...]] = {}
        self._product_categories: dict[int, str] = {}
        self._currency = "₽"
        self.equipment_rows: tuple[EquipmentItem, ...] = ()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(7)
        header = QHBoxLayout()
        header.setSpacing(0)
        self.back_button = action_button(tr("←  К СПИСКУ СОХРАНЕНИЙ"), self)
        self.back_button.setFixedSize(222, 33)
        self.back_button.clicked.connect(self.back_requested)
        header.addWidget(self.back_button)
        header.addSpacing(17)
        self.breadcrumb_separator = QFrame(self)
        self.breadcrumb_separator.setObjectName("editorBreadcrumbSeparator")
        self.breadcrumb_separator.setFrameShape(QFrame.Shape.VLine)
        self.breadcrumb_separator.setFixedSize(1, 38)
        header.addWidget(self.breadcrumb_separator)
        header.addSpacing(40)
        self.breadcrumb = QLabel(tr("Сохранение не открыто"), self)
        self.breadcrumb.setObjectName("editorBreadcrumb")
        header.addWidget(self.breadcrumb, 1)
        self.discard_button = action_button(tr("ОТМЕНИТЬ ВСЕ ИЗМЕНЕНИЯ"), self)
        self.discard_button.setObjectName("editorDiscardButton")
        self.discard_button.setFixedHeight(28)
        self.discard_button.setVisible(False)
        self.discard_button.clicked.connect(self.discard_requested)
        header.addWidget(self.discard_button)
        self.compare_button = action_button(tr("СРАВНИТЬ…"), self)
        self.compare_button.setObjectName("editorCompareButton")
        self.compare_button.setFixedHeight(28)
        self.compare_button.setToolTip(tr("Сравнить открытое сохранение с другим файлом"))
        self.compare_button.clicked.connect(self.compare_requested)
        header.addWidget(self.compare_button)
        header.addSpacing(8)
        self.header_status = status_chip(tr("НЕТ ОТКРЫТОГО СОХРАНЕНИЯ"), self, tone="neutral")
        self.header_status.setFixedHeight(28)
        header.addWidget(self.header_status)
        root.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(0)
        self.status_column = panel(self, object_name="editorStatusColumn")
        status_layout = QVBoxLayout(self.status_column)
        status_layout.setContentsMargins(14, 8, 12, 8)
        status_layout.setSpacing(6)
        status_layout.addWidget(section_header(tr("СТАТУС СОХРАНЕНИЯ"), parent=self.status_column))
        self.money_label = QLabel(tr("ДЕНЬГИ  — ₽"), self.status_column)
        self.money_label.setObjectName("editorMetric")
        self.money_label.setVisible(False)
        money_controls = QHBoxLayout()
        money_controls.setContentsMargins(8, 0, 0, 0)
        money_controls.setSpacing(8)
        self.money_icon = QLabel(self.status_column)
        self.money_icon.setObjectName("editorMetricIcon")
        self.money_icon.setPixmap(
            QIcon(str(_SHELL_ICONS / "currency.svg")).pixmap(QSize(24, 24))
        )
        self.money_icon.setAccessibleName(tr("Деньги"))
        money_controls.addWidget(self.money_icon)
        self.money_spin = QSpinBox(self.status_column)
        self.money_spin.setRange(0, 2_000_000_000)
        self.money_spin.setSuffix(" ₽")
        # Stage on Enter/focus-out, not on every typed digit.
        self.money_spin.setKeyboardTracking(False)
        self.money_spin.setGroupSeparatorShown(True)
        self.money_spin.setLocale(QLocale("ru_RU"))
        self.money_spin.setObjectName("editorMoneySpin")
        self.money_spin.setEnabled(False)
        money_controls.addWidget(self.money_spin, 1)
        self.money_spin.valueChanged.connect(self.money_stage_requested)
        self.money_clear_button = action_button("×", self.status_column)
        self.money_clear_button.setEnabled(False)
        self.money_clear_button.setVisible(False)
        self.money_clear_button.clicked.connect(self.money_clear_requested)
        money_controls.addWidget(self.money_clear_button)
        status_layout.addLayout(money_controls)
        weight_controls = QHBoxLayout()
        weight_controls.setContentsMargins(8, 0, 0, 0)
        weight_controls.setSpacing(8)
        self.weight_icon = QLabel(self.status_column)
        self.weight_icon.setObjectName("editorMetricIcon")
        self.weight_icon.setPixmap(
            QIcon(str(_SHELL_ICONS / "weight.svg")).pixmap(QSize(24, 24))
        )
        self.weight_icon.setAccessibleName(tr("Вес"))
        weight_controls.addWidget(self.weight_icon)
        self.weight_label = QLabel(tr("— кг"), self.status_column)
        self.weight_label.setObjectName("editorMetric")
        weight_controls.addWidget(self.weight_label, 1)
        status_layout.addLayout(weight_controls)
        self.source_label = self._add_info_row(status_layout, tr("Источник"), "library")
        self.integrity_label = self._add_info_row(status_layout, tr("Проверка"), "verified")
        self.capability_label = self._add_info_row(status_layout, tr("Статус"), "equipment")
        status_layout.addSpacing(12)
        self.equipment_scroll = QScrollArea(self.status_column)
        self.equipment_scroll.setObjectName("equipmentScroll")
        self.equipment_scroll.setWidgetResizable(True)
        self.equipment_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.equipment_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.equipment_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.equipment_content = QWidget(self.equipment_scroll)
        self.equipment_content.setObjectName("equipmentContent")
        equipment_content_layout = QVBoxLayout(self.equipment_content)
        equipment_content_layout.setContentsMargins(0, 0, 4, 0)
        equipment_content_layout.setSpacing(6)
        self.equipment_section_header = section_header(
            tr("ЭКИПИРОВКА"), parent=self.equipment_content
        )
        self.equipment_section_header.setFixedHeight(31)
        equipment_content_layout.addWidget(self.equipment_section_header)
        self.equipment_list = QVBoxLayout()
        self.equipment_list.setSpacing(4)
        equipment_content_layout.addLayout(self.equipment_list)
        self.artifact_heading = QLabel(tr("АРТЕФАКТЫ"), self.equipment_content)
        self.artifact_heading.setObjectName("editorInfo")
        equipment_content_layout.addWidget(self.artifact_heading)
        self.artifact_list = QHBoxLayout()
        self.artifact_list.setSpacing(5)
        equipment_content_layout.addLayout(self.artifact_list)
        self.repair_all_button = action_button(tr("ПОЧИНИТЬ ВСЁ ДО 100%"), self.equipment_content)
        self.repair_all_button.setObjectName("repairAllButton")
        self.repair_all_button.setToolTip(
            tr("Подготовить ремонт всего повреждённого снаряжения, для которого запись подтверждена")
        )
        self.repair_all_button.setVisible(False)
        self.repair_all_button.clicked.connect(self.repair_all_requested)
        equipment_content_layout.addWidget(self.repair_all_button)
        self.character_button = action_button(tr("ПЕРСОНАЖ И ГРУППИРОВКИ"), self.equipment_content)
        self.character_button.clicked.connect(self.character_requested)
        self.character_button.setVisible(False)
        equipment_content_layout.addWidget(self.character_button)
        equipment_content_layout.addStretch(1)
        self.equipment_scroll.setWidget(self.equipment_content)
        status_layout.addWidget(self.equipment_scroll, 1)
        self.status_column.setFixedWidth(362)
        columns.addWidget(self.status_column, 0)

        self.inventory_column = panel(self, object_name="editorInventoryColumn")
        inventory_layout = QVBoxLayout(self.inventory_column)
        inventory_layout.setContentsMargins(14, 8, 14, 8)
        inventory_layout.setSpacing(3)
        inventory_controls = QVBoxLayout()
        inventory_controls.setSpacing(8)
        inventory_header = QHBoxLayout()
        inventory_header.addWidget(section_header(tr("ИНВЕНТАРЬ"), parent=self.inventory_column), 1)
        self.item_count_label = QLabel(tr("Предметов: 0"), self.inventory_column)
        inventory_header.addWidget(self.item_count_label)
        self.add_button = action_button(tr("+ ДОБАВИТЬ"), self.inventory_column)
        self.add_button.setObjectName("inventoryAddButton")
        self.add_button.setToolTip(tr("Добавить предмет из каталога выбранной игры"))
        self.add_button.setVisible(False)
        self.add_button.clicked.connect(self.add_requested)
        inventory_header.addWidget(self.add_button)
        inventory_controls.addLayout(inventory_header)
        self.search_edit = QLineEdit(self.inventory_column)
        self.search_edit.setObjectName("referenceSearch")
        self.search_edit.setMinimumHeight(39)
        self.search_edit.setPlaceholderText(tr("Поиск предметов…"))
        self.search_edit.textChanged.connect(self.model.set_search)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self.search_edit, 1)
        self.group_check = QCheckBox(tr("Объединять одинаковые"), self.inventory_column)
        self.group_check.setObjectName("inventoryGroupToggle")
        self.group_check.setToolTip(
            tr("Одинаковые предметы показываются одной строкой. Выключи, чтобы изменить или удалить один из них.")
        )
        self.group_check.setChecked(True)
        self.group_check.toggled.connect(self._set_grouped)
        search_row.addWidget(self.group_check)
        inventory_controls.addLayout(search_row)
        categories = QHBoxLayout()
        categories.setSpacing(4)
        self.category_buttons: list[QPushButton] = []
        for label, value in _CATEGORY_TABS:
            button = QPushButton(label, self.inventory_column)
            button.setToolTip(label.capitalize())
            button.setObjectName("categoryButton")
            # Qt's Fusion style adds the inherited button padding back to the
            # size hint after the app stylesheet is installed. Keep the tab
            # strip at the canonical 32 px height explicitly.
            button.setStyleSheet(
                "QPushButton#categoryButton { padding: 0 8px; min-height: 32px; max-height: 32px; }"
            )
            button.setFixedHeight(32)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, category=value: self._set_category(category))
            categories.addWidget(button)
            self.category_buttons.append(button)
        self.category_buttons[0].setChecked(True)
        inventory_controls.addLayout(categories)
        inventory_layout.addLayout(inventory_controls)
        self.table = QTableView(self.inventory_column)
        self.table.setObjectName("referenceTable")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.setItemDelegateForColumn(
            InventoryTableModel.CONDITION_COLUMN,
            ConditionBarDelegate(self.table),
        )
        self.table.setIconSize(QSize(38, 38))
        self.table.verticalHeader().setDefaultSectionSize(41)
        # Technical evidence remains in the model and tooltips, while the
        # canonical editor presents the compact product hierarchy: name,
        # category, count, weight and condition.  Leaving every diagnostic
        # column visible creates the admin-table appearance rejected by the
        # reference screen.
        for column in (
            InventoryTableModel.POSITION_COLUMN,
            InventoryTableModel.SIZE_COLUMN,
            InventoryTableModel.TYPE_KEY_COLUMN,
            InventoryTableModel.SUPPORT_COLUMN,
            InventoryTableModel.HANDLE_COLUMN,
        ):
            self.table.setColumnHidden(column, True)
        self.table.horizontalHeader().setSectionResizeMode(
            InventoryTableModel.NAME_COLUMN,
            QHeaderView.ResizeMode.Interactive,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            InventoryTableModel.CATEGORY_COLUMN,
            QHeaderView.ResizeMode.Interactive,
        )
        self.table.horizontalHeader().setFixedHeight(34)
        self.table.setColumnWidth(InventoryTableModel.NAME_COLUMN, 250)
        self.table.setColumnWidth(InventoryTableModel.CATEGORY_COLUMN, 145)
        self.table.selectionModel().currentRowChanged.connect(self._on_selection_changed)
        inventory_layout.addWidget(self.table, 1)
        columns.addWidget(self.inventory_column, 1)
        columns.addSpacing(9)

        self.detail_column = panel(self, object_name="editorDetailColumn")
        detail_layout = QVBoxLayout(self.detail_column)
        detail_layout.setContentsMargins(6, 0, 6, 8)
        self.detail_view = ItemDetailView(self.detail_column)
        self.detail_view.count_stage_requested.connect(self.stack_stage_requested)
        self.detail_view.durability_stage_requested.connect(self.durability_stage_requested)
        self.detail_view.placement_stage_requested.connect(self.placement_stage_requested)
        self.detail_view.remove_requested.connect(self.remove_requested)
        self.detail_view.reset_requested.connect(self.reset_requested)
        self.detail_view.upgrades_stage_requested.connect(self.upgrades_stage_requested)
        detail_layout.addWidget(self.detail_view)
        self.detail_column.setFixedWidth(393)
        columns.addWidget(self.detail_column, 0)
        root.addLayout(columns, 1)

        self.save_button = self.detail_view.save_button
        self.save_button.clicked.connect(self.save_requested)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        # Below the canonical width the inventory would otherwise lose its
        # count/weight/condition columns behind a horizontal scrollbar.
        compact = self.width() < 1380
        if getattr(self, "_compact", None) == compact:
            return
        self._compact = compact
        self.status_column.setFixedWidth(290 if compact else 362)
        self.detail_column.setFixedWidth(360 if compact else 393)
        self.detail_view.set_compact(compact)
        self.table.setColumnHidden(InventoryTableModel.CATEGORY_COLUMN, compact)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            InventoryTableModel.NAME_COLUMN,
            QHeaderView.ResizeMode.Stretch if compact else QHeaderView.ResizeMode.Interactive,
        )
        for column in (
            InventoryTableModel.COUNT_COLUMN,
            InventoryTableModel.WEIGHT_COLUMN,
        ):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents if compact else QHeaderView.ResizeMode.Interactive,
            )
        if not compact:
            self.table.setColumnWidth(InventoryTableModel.NAME_COLUMN, 250)
        labels = _COMPACT_CATEGORY_LABELS if compact else tuple(label for label, _value in _CATEGORY_TABS)
        for button, label in zip(self.category_buttons, labels, strict=True):
            button.setText(label)

    def _add_info_row(
        self,
        parent_layout: QVBoxLayout,
        label_text: str,
        icon_name: str,
    ) -> QLabel:
        row = QFrame(self.status_column)
        row.setObjectName("editorInfoRow")
        row.setFixedHeight(30)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(3, 0, 6, 0)
        layout.setSpacing(6)
        label = QLabel(label_text, row)
        label.setObjectName("editorInfoLabel")
        label.setFixedWidth(136)
        layout.addWidget(label)
        icon = QLabel(row)
        icon.setObjectName("editorInfoIcon")
        icon.setFixedSize(18, 18)
        icon.setPixmap(
            QIcon(str(_SHELL_ICONS / f"{icon_name}.svg")).pixmap(QSize(18, 18))
        )
        icon.setAccessibleName(label_text)
        layout.addWidget(icon)
        value = QLabel("—", row)
        value.setObjectName("editorInfoValue")
        value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(value, 1)
        parent_layout.addWidget(row)
        return value

    def _set_category(self, category: str) -> None:
        values = tuple(value for _label, value in _CATEGORY_TABS)
        for button, value in zip(self.category_buttons, values, strict=True):
            button.setChecked(value == category)
        self.model.set_category(category)

    def set_snapshot(self, snapshot: Any) -> None:
        self._capabilities = snapshot.capabilities
        self._catalog = snapshot.catalog
        release_id = str(
            getattr(snapshot, "release_id", "")
            or getattr(snapshot, "format_id", "")
        )
        self._release_id = release_id
        self.detail_view.set_release(release_id)
        game_catalog = getattr(snapshot, "game_catalog", None)
        self._upgrade_catalog = (
            game_catalog.upgrades
            if game_catalog is not None
            and game_catalog.release_id == release_id
            else None
        )
        # Names and icons may come from the modded game the save belongs to.
        self._display_catalog = getattr(snapshot, "display_catalog", None) or self._catalog
        self._icon_resolver = XRayIconResolver(
            self._display_catalog,
            donor=donor_resolver_for(self._catalog),
        )
        self._items = tuple(snapshot.info.inventory)
        self.equipment_rows = equipment_items(
            self._items,
            release_id=release_id,
            catalog=self._catalog,
        )
        self._product_categories = {row.handle: row.category for row in self.equipment_rows}
        self.model.set_icon_provider(self._icon_for_item)
        self.model.set_name_provider(self._name_for_item)
        self.model.set_category_provider(
            lambda item: self._product_categories.get(item.handle)
        )
        self.model.set_items(self._items)
        self.model.sort(InventoryTableModel.POSITION_COLUMN)
        self.item_count_label.setText(tr("Предметов: {0}", len(self._items)))
        self.breadcrumb.setText(f"{snapshot.format_title}  ›  {snapshot.path.name}")
        writable = any(
            snapshot.capabilities.support(name).writable
            for name in ("edit_money", "edit_stacks", "edit_durability")
        )
        self.header_status.setText(tr("МОЖНО ИЗМЕНЯТЬ") if writable else tr("ТОЛЬКО ЧТЕНИЕ"))
        self.header_status.setProperty("tone", "success" if writable else "neutral")
        self.header_status.style().unpolish(self.header_status)
        self.header_status.style().polish(self.header_status)
        self._currency = currency_suffix(release_id)
        self.money_spin.setSuffix(f" {self._currency}")
        money = human_money(snapshot.info.money) if snapshot.info.money is not None else "—"
        self.money_label.setText(tr("ДЕНЬГИ  {0} {1}", money, self._currency))
        self.money_spin.blockSignals(True)
        self.money_spin.setValue(int(snapshot.info.money or 0))
        self.money_spin.blockSignals(False)
        money_writable = bool(
            snapshot.capabilities.edit_money
            and snapshot.info.money is not None
            and snapshot.info.money_anchor_count == 1
        )
        self.money_spin.setEnabled(money_writable)
        self.money_clear_button.setEnabled(False)
        weight = sum(item.total_weight or 0.0 for item in self._items) if all(item.total_weight is not None for item in self._items) else None
        self.weight_label.setText(tr("{0:.1f} кг", weight) if weight is not None else tr("— кг"))
        self.source_label.setText("Steam Cloud" if snapshot.source_kind == "cloud" else tr("Локальный"))
        self.integrity_label.setText(
            tr("Файл проверен") if snapshot.info.crc_ok else tr("Файл повреждён или изменён")
        )
        self.integrity_label.setToolTip("")
        self.integrity_label.setProperty(
            "integrityState", "passed" if snapshot.info.crc_ok else "warning"
        )
        self.integrity_label.style().unpolish(self.integrity_label)
        self.integrity_label.style().polish(self.integrity_label)
        self.capability_label.setText(
            tr("Можно изменять")
            if self.header_status.text() == tr("МОЖНО ИЗМЕНЯТЬ")
            else tr("Только чтение")
        )
        self._render_equipment_summary()
        self.character_button.setVisible(is_xray_original_release(release_id.casefold()))
        self.repair_all_button.setVisible(
            any(row.damaged and row.durability_editable for row in self.equipment_rows)
            and bool(snapshot.capabilities.edit_durability)
        )
        self.add_button.setVisible(bool(snapshot.capabilities.add_items and self._catalog is not None))
        self.selected_handle = None
        self.detail_view.set_item(None, self._capabilities)
        self.detail_view.set_item_icon(None)
        if self.model.visible_items():
            self.table.selectRow(0)

    def _loadout_rows(self) -> tuple[tuple[EquipmentItem, ...], bool]:
        """Return the cards to show and whether they are the equipped set.

        X-Ray and S2 saves expose an explicit equipped state for many rows.
        When a save does not, the panel shows the best owned gear and says so
        instead of calling the first weapon in the list "primary".
        """

        wanted = {"weapon", "armor", "helmet", "device"}
        rows = [row for row in self.equipment_rows if row.category in wanted]
        equipped = [row for row in rows if row.location == "equipped"]
        chosen = equipped or rows

        def rank(row: EquipmentItem) -> tuple[int, int, str]:
            low = row.type_key.casefold().startswith(_LOW_PRIORITY_KEYS)
            if row.category == "device" and row.device_subtype == "detector":
                category_rank = 3
            else:
                category_rank = _LOADOUT_PRIORITY.get(row.category, 5)
            return (int(low), category_rank, row.name.casefold())

        return tuple(sorted(chosen, key=rank)[:6]), bool(equipped)

    def _card_title(self, row: EquipmentItem) -> str:
        if row.category == "weapon":
            return tr("ОРУЖИЕ")
        if row.category == "armor":
            return tr("БРОНЯ")
        if row.category == "helmet":
            return tr("ШЛЕМ")
        return _DEVICE_CARD_TITLES.get(str(row.device_subtype), tr("УСТРОЙСТВО"))

    def _render_equipment_summary(self) -> None:
        while self.equipment_list.count():
            item = self.equipment_list.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        rows, equipped = self._loadout_rows()
        heading = self.equipment_section_header.findChild(QLabel, "sectionHeading")
        if heading is not None:
            heading.setText(tr("ЭКИПИРОВКА") if equipped or not rows else tr("СНАРЯЖЕНИЕ"))
        self.equipment_section_header.setToolTip(
            ""
            if equipped
            else tr("В сохранении не отмечено, что надето; показано снаряжение из инвентаря.")
        )
        if not rows:
            empty = QLabel(tr("Оружие и броня в сохранении не найдены."), self.equipment_content)
            empty.setObjectName("editorInfo")
            empty.setWordWrap(True)
            self.equipment_list.addWidget(empty)
        for offset in range(0, len(rows), 2):
            row_host = QWidget(self.equipment_content)
            row_host.setObjectName("equipmentCardRow")
            row_layout = QHBoxLayout(row_host)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(5)
            current_rows = rows[offset:offset + 2]
            for equipment in current_rows:
                name = (
                    self._name_for_handle(equipment.handle)
                    or equipment.name
                    or tr("Неизвестный предмет")
                )
                button = QToolButton(row_host)
                button.setText("")
                button.setObjectName("equipmentSlot")
                slot_title = self._card_title(equipment)
                button.setAccessibleName(f"{slot_title}: {name}")
                card_layout = QVBoxLayout(button)
                card_layout.setContentsMargins(7, 4, 7, 4)
                card_layout.setSpacing(1)
                caption = QLabel(slot_title, button)
                caption.setObjectName("equipmentSlotCaption")
                caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                card_layout.addWidget(caption)
                item_icon = fit_icon(
                    self._icon_resolver.icon_for_item(
                        equipment.type_key,
                        equipment.name,
                        equipment.category,
                        size=120,
                    ),
                    120,
                    72,
                )
                artwork = QLabel(button)
                artwork.setObjectName("equipmentSlotArtwork")
                artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
                artwork.setPixmap(item_icon.pixmap(QSize(120, 72)))
                artwork.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                card_layout.addWidget(artwork, 1)
                item_name = QLabel(name, button)
                item_name.setObjectName("equipmentSlotName")
                item_name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                item_name.setMaximumWidth(150)
                metrics = item_name.fontMetrics()
                item_name.setText(metrics.elidedText(name, Qt.TextElideMode.ElideRight, 150))
                card_layout.addWidget(item_name)
                button.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
                button.setMinimumHeight(120)
                condition = (
                    tr(" · состояние {0}%", round(equipment.condition * 100))
                    if equipment.condition is not None
                    else ""
                )
                button.setToolTip(tr("{0}{1}\nНажми, чтобы выбрать предмет в инвентаре", name, condition))
                button.clicked.connect(
                    lambda _checked=False, handle=equipment.handle: self._select_everywhere(handle)
                )
                row_layout.addWidget(button, 1)
            if len(current_rows) == 1:
                row_layout.addStretch(1)
            self.equipment_list.addWidget(row_host)
        artifacts = [
            row
            for row in self.equipment_rows
            if row.category == "artifact" and row.location in {"belt", "equipped"}
        ][:5]
        while self.artifact_list.count():
            item = self.artifact_list.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.artifact_heading.setText(tr("АРТЕФАКТЫ НА ПОЯСЕ") if artifacts else tr("НА ПОЯСЕ НЕТ АРТЕФАКТОВ"))
        for artifact in artifacts:
            name = self._name_for_handle(artifact.handle) or artifact.name or tr("Артефакт")
            artifact_button = QPushButton(self.equipment_content)
            artifact_button.setObjectName("artifactSlot")
            artifact_button.setIcon(
                fit_icon(
                    self._icon_resolver.icon_for_item(
                        artifact.type_key,
                        artifact.name,
                        artifact.category,
                        size=52,
                    ),
                    48,
                    48,
                )
            )
            artifact_button.setIconSize(QSize(48, 48))
            artifact_button.setFixedSize(64, 64)
            artifact_button.setToolTip(name)
            artifact_button.clicked.connect(
                lambda _checked=False, handle=artifact.handle: self._select_everywhere(handle)
            )
            self.artifact_list.addWidget(artifact_button)
        self.artifact_list.addStretch(1)

    def _name_for_handle(self, handle: int) -> str | None:
        item = next((candidate for candidate in self._items if candidate.handle == handle), None)
        return self._name_for_item(item) if item is not None else None

    def _select_everywhere(self, handle: int) -> None:
        """Select a loadout item even when the current tab/search hides it."""

        if handle not in {item.handle for item in self.model.visible_items()}:
            self.search_edit.clear()
            self._set_category("all")
        self.select_handle(handle)

    def icon_for_definition(self, definition) -> QIcon:
        return self._icon_resolver.icon_for(definition, size=32)

    def _icon_for_item(self, item: InventoryItem):
        return fit_icon(
            self._icon_resolver.icon_for_item(
                item.type_key,
                item.display_name,
                self._product_categories.get(item.handle) or item.category,
                size=52,
            ),
            52,
            52,
        )

    def _name_for_item(self, item: InventoryItem) -> str | None:
        display = getattr(self, "_display_catalog", None)
        catalog = display or self._catalog
        return item_label(
            item,
            catalog,
            stalker2=self._is_stalker2(),
            release_id=getattr(self, "_release_id", None),
            modded=display is not None and display is not self._catalog,
        )

    def _is_stalker2(self) -> bool:
        return str(getattr(self, "_release_id", "") or "").startswith("stalker2")

    def select_handle(self, handle: int) -> None:
        visible = self.model.visible_items()
        row = next((index for index, item in enumerate(visible) if item.handle == handle), None)
        if row is not None:
            self.table.selectRow(row)

    def _set_grouped(self, enabled: bool) -> None:
        current = self.detail_view._item
        self.model.set_grouped(enabled)
        if current is not None:
            self.select_handle(current.handle)

    def _show_detail(self, item: InventoryItem | None) -> None:
        self.detail_view.set_item(
            item,
            self._capabilities,
            upgrade_catalog=self._upgrade_catalog,
            staged_counts=self._staged_counts,
            staged_durability=self._staged_durability,
            removed_handles=self._removed_handles,
            staged_placements=self._staged_placements,
            staged_upgrades=self._staged_upgrades,
            display_name=self._name_for_item(item) if item is not None else None,
            category_key=self._product_categories.get(item.handle) if item is not None else None,
            group_size=len(self.model.group_members(item)),
        )
        self.detail_view.set_item_icon(self._detail_icon(item) if item is not None else None)

    def _on_selection_changed(self, current, _previous) -> None:
        item = self.model.item_at(current.row()) if current.isValid() else None
        if item is None or item.handle != self.selected_handle:
            # A refusal message belongs to the item it was about.
            self.detail_view.module_status.setText("")
        self.selected_handle = item.handle if item is not None else None
        self._show_detail(item)

    def set_draft(
        self,
        *,
        counts: Mapping[int, int],
        durability: Mapping[int, float],
        removed: Mapping[int, bool],
        change_count: int,
        placements: Mapping[int, tuple[str, int | None]] | None = None,
        upgrades: Mapping[int, tuple[str, ...]] | None = None,
    ) -> None:
        self._staged_counts = counts
        self._staged_durability = durability
        self._removed_handles = removed
        self._staged_placements = placements or {}
        self._staged_upgrades = upgrades or {}
        self.model.set_staged_counts(counts)
        self.model.set_staged_durability(durability)
        self.model.set_staged_placements(self._staged_placements)
        self.model.set_changed_handles(
            set(counts)
            | set(durability)
            | set(removed)
            | set(self._staged_placements)
            | set(self._staged_upgrades)
        )
        self.detail_view.set_change_count(change_count)
        self.discard_button.setVisible(change_count > 0)
        current = self.selected_handle
        visible_handles = {item.handle for item in self.model.visible_items()}
        if current not in visible_handles:
            current = next(
                (item.handle for item in self.model.visible_items()),
                None,
            )
        self.selected_handle = current
        if current is not None:
            self.select_handle(current)
        item = next((candidate for candidate in self._items if candidate.handle == current), None)
        self._show_detail(item)

    def _detail_icon(self, item: InventoryItem):
        return fit_icon(
            self._icon_resolver.icon_for_item(
                item.type_key,
                item.display_name,
                self._product_categories.get(item.handle) or item.category,
                size=420,
            ),
            380,
            86,
        )

    def set_money_draft(self, value: int | None) -> None:
        if value is None:
            return
        self.money_label.setText(tr("ДЕНЬГИ  {0} {1}", human_money(value), self._currency))
        self.money_spin.blockSignals(True)
        self.money_spin.setValue(value)
        self.money_spin.blockSignals(False)
        self.money_clear_button.setEnabled(True)

    def show_capability_message(self, message: str) -> None:
        self.detail_view.module_status.setText(message)
        self.detail_view.module_status.setToolTip("")


__all__ = ["EditorView"]
