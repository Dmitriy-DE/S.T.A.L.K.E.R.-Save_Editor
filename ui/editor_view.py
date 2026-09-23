"""Canonical three-column save editor surface."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from editor.capabilities import FormatCapabilities
from editor.catalog import ItemCatalog
from save_format import InventoryItem

from .inventory_model import InventoryTableModel
from .item_detail_view import ItemDetailView
from .style_components import action_button, panel, section_header, status_chip
from .xray_assets import XRayIconResolver


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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("editorView")
        self.model = InventoryTableModel(self)
        self.model.set_name_provider(lambda item: item.display_name)
        self.selected_handle: int | None = None
        self._items: tuple[InventoryItem, ...] = ()
        self._capabilities: FormatCapabilities | None = None
        self._catalog: ItemCatalog | None = None
        self._icon_resolver = XRayIconResolver(None)
        self._staged_counts: Mapping[int, int] = {}
        self._staged_durability: Mapping[int, float] = {}
        self._removed_handles: Mapping[int, bool] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 10, 0, 0)
        root.setSpacing(8)
        header = QHBoxLayout()
        self.back_button = action_button("←  К СПИСКУ СОХРАНЕНИЙ", self)
        self.back_button.clicked.connect(self.back_requested)
        header.addWidget(self.back_button)
        self.breadcrumb = QLabel("Сохранение не открыто", self)
        self.breadcrumb.setObjectName("editorBreadcrumb")
        header.addWidget(self.breadcrumb, 1)
        self.header_status = status_chip("НЕТ SNAPSHOT", self, tone="neutral")
        header.addWidget(self.header_status)
        root.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(10)
        self.status_column = panel(self, object_name="editorStatusColumn")
        status_layout = QVBoxLayout(self.status_column)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)
        status_layout.addWidget(section_header("СТАТУС СОХРАНЕНИЯ", parent=self.status_column))
        self.money_label = QLabel("◉  —", self.status_column)
        self.money_label.setObjectName("editorMetric")
        status_layout.addWidget(self.money_label)
        self.weight_label = QLabel("⚖  —", self.status_column)
        self.weight_label.setObjectName("editorMetric")
        status_layout.addWidget(self.weight_label)
        self.source_label = QLabel("Источник\n—", self.status_column)
        self.source_label.setObjectName("editorInfo")
        status_layout.addWidget(self.source_label)
        self.integrity_label = QLabel("Целостность\n—", self.status_column)
        self.integrity_label.setObjectName("editorInfo")
        status_layout.addWidget(self.integrity_label)
        self.capability_label = QLabel("Статус\n—", self.status_column)
        self.capability_label.setObjectName("editorInfo")
        status_layout.addWidget(self.capability_label)
        status_layout.addWidget(section_header("ЭКИПИРОВКА", parent=self.status_column))
        self.equipment_list = QVBoxLayout()
        self.equipment_list.setSpacing(4)
        status_layout.addLayout(self.equipment_list)
        self.character_button = action_button("ПЕРСОНАЖ И ГРУППИРОВКИ", self.status_column)
        self.character_button.clicked.connect(self.character_requested)
        self.character_button.setVisible(False)
        status_layout.addWidget(self.character_button)
        status_layout.addStretch(1)
        columns.addWidget(self.status_column, 24)

        self.inventory_column = panel(self, object_name="editorInventoryColumn")
        inventory_layout = QVBoxLayout(self.inventory_column)
        inventory_layout.setContentsMargins(12, 12, 12, 12)
        inventory_layout.setSpacing(8)
        inventory_header = QHBoxLayout()
        inventory_header.addWidget(section_header("ИНВЕНТАРЬ", parent=self.inventory_column), 1)
        self.item_count_label = QLabel("Элементов: 0", self.inventory_column)
        inventory_header.addWidget(self.item_count_label)
        inventory_layout.addLayout(inventory_header)
        self.search_edit = QLineEdit(self.inventory_column)
        self.search_edit.setObjectName("referenceSearch")
        self.search_edit.setPlaceholderText("⌕  Поиск по названию, типу, категории…")
        self.search_edit.textChanged.connect(self.model.set_search)
        inventory_layout.addWidget(self.search_edit)
        categories = QHBoxLayout()
        categories.setSpacing(4)
        self.category_buttons: list[QPushButton] = []
        for label, value in (("ВСЕ", "Все"), ("ОРУЖИЕ", "weapon"), ("БОЕПРИПАСЫ", "ammo"), ("СНАРЯЖЕНИЕ", "armor"), ("РАСХОДНИКИ", "consumable"), ("АРТЕФАКТЫ", "artifact"), ("КЛЮЧИ", "quest"), ("ПРОЧЕ", "other")):
            button = QPushButton(label, self.inventory_column)
            button.setObjectName("categoryButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, category=value: self._set_category(category))
            categories.addWidget(button)
            self.category_buttons.append(button)
        self.category_buttons[0].setChecked(True)
        inventory_layout.addLayout(categories)
        self.table = QTableView(self.inventory_column)
        self.table.setObjectName("referenceTable")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setIconSize(QSize(34, 34))
        self.table.selectionModel().currentRowChanged.connect(self._on_selection_changed)
        inventory_layout.addWidget(self.table, 1)
        columns.addWidget(self.inventory_column, 49)

        self.detail_column = panel(self, object_name="editorDetailColumn")
        detail_layout = QVBoxLayout(self.detail_column)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        self.detail_view = ItemDetailView(self.detail_column)
        self.detail_view.count_stage_requested.connect(self.stack_stage_requested)
        self.detail_view.durability_stage_requested.connect(self.durability_stage_requested)
        self.detail_view.placement_stage_requested.connect(self.placement_stage_requested)
        self.detail_view.remove_requested.connect(self.remove_requested)
        self.detail_view.reset_requested.connect(self.reset_requested)
        detail_layout.addWidget(self.detail_view)
        columns.addWidget(self.detail_column, 27)
        root.addLayout(columns, 1)

        self.save_button = self.detail_view.save_button
        self.save_button.clicked.connect(self.save_requested)

    def _set_category(self, category: str) -> None:
        for button in self.category_buttons:
            button.setChecked(button is self.sender())
        if category == "Все":
            self.model.set_category("Все")
        else:
            self.model.set_category(category)

    def set_snapshot(self, snapshot: Any) -> None:
        self._capabilities = snapshot.capabilities
        self._catalog = snapshot.catalog
        self._icon_resolver = XRayIconResolver(self._catalog)
        self.model.set_icon_provider(self._icon_for_item)
        self.model.set_name_provider(self._name_for_item)
        self._items = tuple(snapshot.info.inventory)
        self.model.set_items(self._items)
        self.item_count_label.setText(f"Элементов: {len(self._items)}")
        self.breadcrumb.setText(f"{snapshot.format_title}  ›  {snapshot.path.name}")
        self.header_status.setText("РЕДАКТИРУЕМЫЙ" if any(snapshot.capabilities.support(name).writable for name in ("edit_money", "edit_stacks", "edit_durability")) else "READ-ONLY")
        self.header_status.setProperty("tone", "success" if self.header_status.text() == "РЕДАКТИРУЕМЫЙ" else "neutral")
        self.header_status.style().unpolish(self.header_status)
        self.header_status.style().polish(self.header_status)
        self.money_label.setText(f"◉  {snapshot.info.money if snapshot.info.money is not None else '—'} ₽")
        weight = sum(item.total_weight or 0.0 for item in self._items) if all(item.total_weight is not None for item in self._items) else None
        self.weight_label.setText(f"⚖  {weight:.1f} кг" if weight is not None else "⚖  — кг")
        self.source_label.setText("Источник\n" + ("Steam Cloud" if snapshot.source_kind == "cloud" else "Локальный"))
        self.integrity_label.setText("Целостность\n" + ("CRC PASS" if snapshot.info.crc_ok else "ПРОВЕРЬТЕ ДАННЫЕ"))
        self.capability_label.setText("Статус\n" + ("Редактируемый" if self.header_status.text() == "РЕДАКТИРУЕМЫЙ" else "Только чтение"))
        self._render_equipment()
        self.selected_handle = None
        self.detail_view.set_item(None, self._capabilities)
        self.detail_view.set_item_icon(None)
        if self.model.visible_items():
            self.table.selectRow(0)

    def _render_equipment(self) -> None:
        while self.equipment_list.count():
            item = self.equipment_list.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        for row in self._items[:6]:
            button = QPushButton(f"▧  {row.display_name or row.type_key}", self.status_column)
            button.setObjectName("equipmentSlot")
            button.setIcon(
                self._icon_resolver.icon_for_item(
                    row.type_key,
                    row.display_name,
                    row.category,
                    size=28,
                )
            )
            button.clicked.connect(lambda _checked=False, handle=row.handle: self.select_handle(handle))
            self.equipment_list.addWidget(button)

    def _icon_for_item(self, item: InventoryItem):
        return self._icon_resolver.icon_for_item(
            item.type_key,
            item.display_name,
            item.category,
            size=30,
        )

    def _name_for_item(self, item: InventoryItem) -> str | None:
        if self._catalog is None:
            return item.display_name
        definition = self._catalog.resolve_key_or_display_name(item.display_name or item.type_key)
        return definition.display_name if definition is not None else item.display_name

    def select_handle(self, handle: int) -> None:
        visible = self.model.visible_items()
        row = next((index for index, item in enumerate(visible) if item.handle == handle), None)
        if row is not None:
            self.table.selectRow(row)

    def _on_selection_changed(self, current, _previous) -> None:
        item = self.model.item_at(current.row()) if current.isValid() else None
        self.selected_handle = item.handle if item is not None else None
        self.detail_view.set_item(
            item,
            self._capabilities,
            staged_counts=self._staged_counts,
            staged_durability=self._staged_durability,
            removed_handles=self._removed_handles,
        )
        self.detail_view.set_item_icon(self._detail_icon(item) if item is not None else None)

    def set_draft(
        self,
        *,
        counts: Mapping[int, int],
        durability: Mapping[int, float],
        removed: Mapping[int, bool],
        change_count: int,
    ) -> None:
        self._staged_counts = counts
        self._staged_durability = durability
        self._removed_handles = removed
        self.model.set_staged_counts(counts)
        self.model.set_staged_durability(durability)
        self.model.set_changed_handles(set(counts) | set(durability) | set(removed))
        self.detail_view.set_change_count(change_count)
        current = self.selected_handle
        item = next((candidate for candidate in self._items if candidate.handle == current), None)
        self.detail_view.set_item(item, self._capabilities, staged_counts=counts, staged_durability=durability, removed_handles=removed)
        self.detail_view.set_item_icon(self._detail_icon(item) if item is not None else None)

    def _detail_icon(self, item: InventoryItem):
        return self._icon_resolver.icon_for_item(
            item.type_key,
            item.display_name,
            item.category,
            size=96,
        )


__all__ = ["EditorView"]
