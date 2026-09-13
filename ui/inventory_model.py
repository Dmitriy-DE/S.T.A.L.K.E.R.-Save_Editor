"""Qt table model for the immutable inventory snapshot.

The parser owns the data model.  This module only presents ``InventoryItem``
values and a separate staged-count map; it never mutates a save payload.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor

from save_format import EDITABLE_STACK_KIND_CODES, InventoryItem


class InventoryTableModel(QAbstractTableModel):
    """Filterable/sortable view of a frozen inventory tuple.

    Rows are always recovered from their ``InventoryItem.handle``.  Filtering
    or sorting therefore cannot redirect a staged edit to another object.
    """

    NAME_COLUMN = 0
    CATEGORY_COLUMN = 1
    POSITION_COLUMN = 2
    SIZE_COLUMN = 3
    TYPE_KEY_COLUMN = 4
    COUNT_COLUMN = 5
    WEIGHT_COLUMN = 6
    SUPPORT_COLUMN = 7
    HANDLE_COLUMN = 8

    HEADERS = (
        "Имя",
        "Категория",
        "Позиция",
        "Размер",
        "Type-key",
        "Количество",
        "Вес",
        "Поддержка",
        "Handle",
    )
    _CHANGED_BRUSH = QBrush(QColor("#fff2cc"))

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: tuple[InventoryItem, ...] = ()
        self._visible: tuple[InventoryItem, ...] = ()
        self._search = ""
        self._category = "Все"
        self._changed_only = False
        self._changed_handles: frozenset[int] = frozenset()
        self._staged_counts: dict[int, int] = {}
        self._sort_column = self.POSITION_COLUMN
        self._sort_order = Qt.SortOrder.AscendingOrder

    @property
    def source_items(self) -> tuple[InventoryItem, ...]:
        """Return the immutable parser snapshot currently shown by the model."""

        return self._items

    def visible_items(self) -> tuple[InventoryItem, ...]:
        """Return the current filtered/sorted rows for stable handle lookup."""

        return self._visible

    def item_at(self, row: int) -> InventoryItem | None:
        if 0 <= row < len(self._visible):
            return self._visible[row]
        return None

    def staged_count(self, handle: int) -> int | None:
        return self._staged_counts.get(int(handle))

    def set_items(self, items: Iterable[InventoryItem]) -> None:
        self._items = tuple(items)
        # A new save snapshot cannot inherit edits from another source file.
        self._staged_counts = {}
        self._rebuild()

    def set_staged_counts(self, counts: Mapping[int, int]) -> None:
        self._staged_counts = {int(handle): int(value) for handle, value in counts.items()}
        self._rebuild()

    def set_search(self, text: str) -> None:
        value = str(text).strip().casefold()
        if value == self._search:
            return
        self._search = value
        self._rebuild()

    def set_category(self, category: str) -> None:
        value = str(category)
        if value == self._category:
            return
        self._category = value
        self._rebuild()

    def set_changed_only(self, enabled: bool) -> None:
        value = bool(enabled)
        if value == self._changed_only:
            return
        self._changed_only = value
        self._rebuild()

    def set_changed_handles(self, handles: Iterable[int]) -> None:
        value = frozenset(int(handle) for handle in handles)
        if value == self._changed_handles:
            return
        self._changed_handles = value
        self._rebuild()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._visible)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        if 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.item_at(index.row())
        if item is None:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(item, index.column())
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(item, index.column())
        if role == Qt.ItemDataRole.BackgroundRole and item.handle in self._staged_counts:
            return self._CHANGED_BRUSH
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in {
            self.COUNT_COLUMN,
            self.WEIGHT_COLUMN,
        }:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        if not 0 <= column < len(self.HEADERS):
            return
        self._sort_column = int(column)
        self._sort_order = Qt.SortOrder(order)
        self._rebuild()

    def _rebuild(self) -> None:
        filtered = [item for item in self._items if self._matches(item)]
        filtered.sort(key=self._sort_key, reverse=self._sort_order == Qt.SortOrder.DescendingOrder)
        self.beginResetModel()
        self._visible = tuple(filtered)
        self.endResetModel()

    def _matches(self, item: InventoryItem) -> bool:
        if self._category != "Все" and item.category != self._category:
            return False
        if self._changed_only and item.handle not in self._changed_handles:
            return False
        if not self._search:
            return True
        haystack = " ".join(
            (
                "Неизвестный объект",
                item.category,
                item.position,
                item.size_text,
                item.type_key,
                item.handle_hex,
                self._support_text(item),
            )
        ).casefold()
        return self._search in haystack

    def _sort_key(self, item: InventoryItem):
        staged = self._staged_counts.get(item.handle)
        count = staged if staged is not None else item.count
        values = {
            self.NAME_COLUMN: "неизвестный объект",
            self.CATEGORY_COLUMN: item.category.casefold(),
            self.POSITION_COLUMN: (item.y, item.x),
            self.SIZE_COLUMN: (item.width * item.height, item.width, item.height),
            self.TYPE_KEY_COLUMN: item.type_key.casefold(),
            self.COUNT_COLUMN: count,
            self.WEIGHT_COLUMN: (staged * item.unit_weight if staged is not None else item.total_weight),
            self.SUPPORT_COLUMN: self._support_text(item).casefold(),
            self.HANDLE_COLUMN: item.handle,
        }
        return (values.get(self._sort_column, ""), item.handle)

    def _display_value(self, item: InventoryItem, column: int) -> str:
        staged = self._staged_counts.get(item.handle)
        if column == self.NAME_COLUMN:
            return "Неизвестный объект"
        if column == self.CATEGORY_COLUMN:
            return item.category
        if column == self.POSITION_COLUMN:
            return item.position
        if column == self.SIZE_COLUMN:
            return item.size_text
        if column == self.TYPE_KEY_COLUMN:
            return f"0x{item.type_key}"
        if column == self.COUNT_COLUMN:
            return str(item.count) if staged is None else f"{item.count} → {staged}"
        if column == self.WEIGHT_COLUMN:
            if staged is None:
                return f"{item.total_weight:.3f}"
            return f"{item.total_weight:.3f} → {staged * item.unit_weight:.3f}"
        if column == self.SUPPORT_COLUMN:
            return self._support_text(item)
        if column == self.HANDLE_COLUMN:
            return item.handle_hex
        return ""

    def _tooltip(self, item: InventoryItem, column: int) -> str:
        if column == self.NAME_COLUMN:
            return (
                "Имя не определено: каталог SID/type-key ещё не подтверждён. "
                f"Type-key: 0x{item.type_key}"
            )
        if column == self.HANDLE_COLUMN:
            return f"Стабильный идентификатор: {item.handle_hex}"
        if column == self.SUPPORT_COLUMN:
            return self._support_text(item)
        return self._display_value(item, column)

    @staticmethod
    def _support_text(item: InventoryItem) -> str:
        if item.editable_count:
            return "Количество можно изменить"
        if item.count <= 1:
            return "Только чтение: count=1"
        if item.kind_code not in EDITABLE_STACK_KIND_CODES:
            return f"Только чтение: неизвестный kind={item.kind_code}"
        return "Только чтение: запись не подтверждена"


__all__ = ["InventoryTableModel"]
