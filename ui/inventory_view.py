"""Inventory controls for the optional Qt shell."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from save_format import EDITABLE_STACK_KIND_CODES, InventoryItem

from .inventory_model import InventoryTableModel


class InventoryView(QWidget):
    """Searchable inventory table with local, unapplied stack staging."""

    stage_requested = Signal(int, int)
    clear_selected_requested = Signal(int)
    clear_all_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = InventoryTableModel(self)
        self.selected_handle: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по type-key, handle, категории…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.model.set_search)
        filters.addWidget(self.search_edit, 2)

        self.category_combo = QComboBox()
        self.category_combo.addItem("Все")
        self.category_combo.currentTextChanged.connect(self.model.set_category)
        filters.addWidget(self.category_combo, 1)

        self.changed_only = QCheckBox("Только изменённые")
        self.changed_only.toggled.connect(self.model.set_changed_only)
        filters.addWidget(self.changed_only)
        layout.addLayout(filters)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(
            InventoryTableModel.POSITION_COLUMN,
            Qt.SortOrder.AscendingOrder,
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.selectionModel().currentRowChanged.connect(self._on_current_row_changed)
        layout.addWidget(self.table, 1)

        editor = QGroupBox("Выбранный предмет")
        form = QFormLayout(editor)
        self.selected_label = QLabel("Строка не выбрана")
        self.selected_label.setWordWrap(True)
        self.selected_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Детали", self.selected_label)

        self.editability_label = QLabel("Выбери строку; неподтверждённые записи остаются read-only.")
        self.editability_label.setWordWrap(True)
        form.addRow("Статус", self.editability_label)

        count_row = QHBoxLayout()
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1_000_000)
        self.count_spin.setEnabled(False)
        self.count_spin.valueChanged.connect(self._on_count_changed)
        count_row.addWidget(self.count_spin)
        self.stage_button = QPushButton("Застейджить количество")
        self.stage_button.setEnabled(False)
        self.stage_button.clicked.connect(self._stage_selected)
        count_row.addWidget(self.stage_button)
        self.clear_selected_button = QPushButton("Очистить выбранное")
        self.clear_selected_button.setEnabled(False)
        self.clear_selected_button.clicked.connect(self._clear_selected)
        count_row.addWidget(self.clear_selected_button)
        self.clear_all_button = QPushButton("Очистить всё")
        self.clear_all_button.setEnabled(False)
        self.clear_all_button.clicked.connect(self.clear_all_requested.emit)
        count_row.addWidget(self.clear_all_button)
        form.addRow("Новое количество", count_row)
        layout.addWidget(editor)

    def set_items(self, items: Iterable[InventoryItem]) -> None:
        values = tuple(items)
        self.model.set_items(values)
        current_category = self.category_combo.currentText()
        categories = sorted({item.category for item in values}, key=str.casefold)
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("Все")
        self.category_combo.addItems(categories)
        if current_category in categories:
            self.category_combo.setCurrentText(current_category)
        else:
            self.category_combo.setCurrentIndex(0)
        self.category_combo.blockSignals(False)
        # ``blockSignals`` above deliberately avoids a transient rebuild while
        # repopulating the combo; apply the final category once afterwards.
        self.model.set_category(self.category_combo.currentText())
        self.search_edit.clear()
        self.changed_only.setChecked(False)
        self.selected_handle = None
        self.table.clearSelection()
        self._update_editor(None)

    def set_staged_counts(self, counts: Mapping[int, int]) -> None:
        selected = self.selected_handle
        self.model.set_staged_counts(counts)
        self.model.set_changed_handles(counts)
        self._restore_selection(selected)
        self.clear_all_button.setEnabled(bool(counts))

    def show_editability_message(self, message: str) -> None:
        self.editability_label.setText(message)

    def _on_current_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        item = self.model.item_at(current.row()) if current.isValid() else None
        self.selected_handle = item.handle if item else None
        self._update_editor(item)

    def _restore_selection(self, handle: int | None) -> None:
        if handle is None:
            self.selected_handle = None
            self.table.clearSelection()
            self._update_editor(None)
            return
        row = next(
            (index for index, item in enumerate(self.model.visible_items()) if item.handle == handle),
            None,
        )
        if row is None:
            self.selected_handle = None
            self.table.clearSelection()
            self._update_editor(None)
            return
        self.table.selectRow(row)
        self.selected_handle = handle
        self._update_editor(self.model.item_at(row))

    def _selected_item(self) -> InventoryItem | None:
        if self.selected_handle is None:
            return None
        return next(
            (item for item in self.model.source_items if item.handle == self.selected_handle),
            None,
        )

    def _update_editor(self, item: InventoryItem | None) -> None:
        if item is None:
            self.selected_label.setText("Строка не выбрана")
            self.editability_label.setText(
                "Выбери строку; неподтверждённые записи остаются read-only."
            )
            self.count_spin.blockSignals(True)
            self.count_spin.setEnabled(False)
            self.count_spin.setValue(1)
            self.count_spin.blockSignals(False)
            self.stage_button.setEnabled(False)
            self.clear_selected_button.setEnabled(False)
            return

        staged = self.model.staged_count(item.handle)
        effective_count = staged if staged is not None else item.count
        self.selected_label.setText(
            f"{item.handle_hex} • type-key 0x{item.type_key} • "
            f"позиция {item.position} • {item.category}"
        )
        if not item.editable_count:
            if item.count <= 1:
                reason = "Только чтение: count=1"
            elif item.kind_code not in EDITABLE_STACK_KIND_CODES:
                reason = f"Только чтение: неизвестный kind={item.kind_code}"
            else:
                reason = "Только чтение: запись не подтверждена"
            self.editability_label.setText(reason)
            self.count_spin.blockSignals(True)
            self.count_spin.setEnabled(False)
            self.count_spin.setValue(item.count)
            self.count_spin.blockSignals(False)
            self.stage_button.setEnabled(False)
            self.clear_selected_button.setEnabled(staged is not None)
            return

        self.editability_label.setText(
            f"Можно изменить количество: {item.count} → {effective_count} "
            "(допустимо 1..1000000; bytes пока не изменены)"
        )
        self.count_spin.blockSignals(True)
        self.count_spin.setEnabled(True)
        self.count_spin.setValue(effective_count)
        self.count_spin.blockSignals(False)
        self.stage_button.setEnabled(True)
        self.clear_selected_button.setEnabled(staged is not None)

    def _on_count_changed(self, _value: int) -> None:
        # The spin box range is the first validation layer.  Keeping the
        # stage button enabled here makes the current→new value explicit.
        item = self._selected_item()
        self.stage_button.setEnabled(item is not None and bool(item.editable_count))

    def _stage_selected(self) -> None:
        item = self._selected_item()
        if item is None or not item.editable_count:
            return
        self.stage_requested.emit(item.handle, self.count_spin.value())

    def _clear_selected(self) -> None:
        if self.selected_handle is not None:
            self.clear_selected_requested.emit(self.selected_handle)


__all__ = ["InventoryView"]
