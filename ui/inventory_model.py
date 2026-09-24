"""Qt table model for the immutable inventory snapshot.

The parser owns the data model.  This module only presents ``InventoryItem``
values and a separate staged-count map; it never mutates a save payload.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import TypeAlias

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QIcon

from editor.equipment import category_label
from save_format import EDITABLE_STACK_KIND_CODES, InventoryItem

# Qt calls these overrides with either index type; narrowing the signature to
# QModelIndex alone is a Liskov violation the type checker rejects once the Qt
# stubs are installed.
ModelIndex: TypeAlias = QModelIndex | QPersistentModelIndex
IconProvider: TypeAlias = Callable[[InventoryItem], QIcon | None]
NameProvider: TypeAlias = Callable[[InventoryItem], str | None]
CategoryProvider: TypeAlias = Callable[[InventoryItem], str | None]

# Inventory tabs group the shared product taxonomy from ``editor.equipment``.
# The parser's own labels ("Патроны", "Гранаты/стак"...) are format-shaped and
# must never be compared with these keys directly.
CATEGORY_TABS: dict[str, frozenset[str]] = {
    "weapon": frozenset({"weapon"}),
    "ammo": frozenset({"ammo"}),
    "armor": frozenset({"armor", "helmet", "device"}),
    "consumable": frozenset({"consumable"}),
    "artifact": frozenset({"artifact"}),
    "quest": frozenset({"quest"}),
    "other": frozenset({"other", "module"}),
}


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
    CONDITION_COLUMN = 7
    SUPPORT_COLUMN = 8
    HANDLE_COLUMN = 9

    HEADERS = (
        "НАЗВАНИЕ",
        "ТИП",
        "Позиция",
        "Размер",
        "Идентификатор типа",
        "КОЛ-ВО",
        "ВЕС (КГ)",
        "СОСТОЯНИЕ",
        "Поддержка",
        "Идентификатор",
    )
    _CHANGED_BRUSH = QBrush(QColor("#fff2cc"))
    _CHANGED_TEXT_BRUSH = QBrush(QColor("#151713"))

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: tuple[InventoryItem, ...] = ()
        self._visible: tuple[InventoryItem, ...] = ()
        self._search = ""
        self._category = "Все"
        self._changed_only = False
        self._changed_handles: frozenset[int] = frozenset()
        self._staged_counts: dict[int, int] = {}
        self._staged_durability: dict[int, float] = {}
        self._staged_placements: dict[int, tuple[str, int | None]] = {}
        self._icon_provider: IconProvider | None = None
        self._name_provider: NameProvider | None = None
        self._category_provider: CategoryProvider | None = None
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

    def set_items(self, items: Iterable[InventoryItem]) -> None:
        self._items = tuple(items)
        # A new save snapshot cannot inherit edits from another source file.
        self._staged_counts = {}
        self._staged_durability = {}
        self._staged_placements = {}
        self._rebuild()

    def set_staged_counts(self, counts: Mapping[int, int]) -> None:
        self._staged_counts = {int(handle): int(value) for handle, value in counts.items()}
        self._rebuild()

    def set_staged_durability(self, durability: Mapping[int, float]) -> None:
        self._staged_durability = {
            int(handle): float(value) for handle, value in durability.items()
        }
        self._rebuild()

    def set_staged_placements(
        self,
        placements: Mapping[int, tuple[str, int | None]],
    ) -> None:
        self._staged_placements = {
            int(handle): (str(value[0]), None if value[1] is None else int(value[1]))
            for handle, value in placements.items()
        }
        self._rebuild()

    def set_icon_provider(self, provider: IconProvider | None) -> None:
        """Set the presentation-only icon source for the name column.

        The callback may read the selected official installation, but it never
        receives save bytes and cannot affect filtering or staged edits.
        """

        self._icon_provider = provider
        self._rebuild()

    def set_name_provider(self, provider: NameProvider | None) -> None:
        """Set a presentation-only catalog/localization name resolver."""

        self._name_provider = provider
        self._rebuild()

    def set_category_provider(self, provider: CategoryProvider | None) -> None:
        """Map rows to the shared product category used by tabs and labels."""

        self._category_provider = provider
        self._rebuild()

    def category_key(self, item: InventoryItem) -> str:
        if self._category_provider is not None:
            try:
                value = self._category_provider(item)
            except Exception:
                value = None
            if value:
                return str(value)
        return "other"

    def category_text(self, item: InventoryItem) -> str:
        if self._category_provider is None:
            return item.category
        return category_label(self.category_key(item))

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

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._visible)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        if 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def flags(self, index: ModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: ModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.item_at(index.row())
        if item is None:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == self.CONDITION_COLUMN:
                # The condition delegate draws the percentage and durability
                # meter together; leaving text here makes Qt paint it again.
                return ""
            return self._display_value(item, index.column())
        if (
            role == Qt.ItemDataRole.AccessibleTextRole
            and index.column() == self.CONDITION_COLUMN
        ):
            return self._display_value(item, index.column())
        if role == Qt.ItemDataRole.DecorationRole and index.column() == self.NAME_COLUMN:
            return self._icon_provider(item) if self._icon_provider is not None else None
        if role == Qt.ItemDataRole.UserRole and index.column() == self.CONDITION_COLUMN:
            staged_condition = self._staged_durability.get(item.handle)
            return item.condition if staged_condition is None else staged_condition
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(item, index.column())
        if role in (Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole) and (
            item.handle in self._changed_handles
            or item.handle in self._staged_counts
            or item.handle in self._staged_durability
            or item.handle in self._staged_placements
        ):
            return (
                self._CHANGED_BRUSH
                if role == Qt.ItemDataRole.BackgroundRole
                else self._CHANGED_TEXT_BRUSH
            )
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in {
            self.COUNT_COLUMN,
            self.WEIGHT_COLUMN,
            self.CONDITION_COLUMN,
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
        if self._category != "Все":
            group = CATEGORY_TABS.get(self._category)
            if group is None:
                if item.category != self._category:
                    return False
            elif self.category_key(item) not in group:
                return False
        if self._changed_only and item.handle not in self._changed_handles:
            return False
        if not self._search:
            return True
        haystack = " ".join(
            (
                self._display_name(item),
                item.category,
                self.category_text(item),
                item.position,
                item.size_text,
                item.type_key,
                item.handle_hex,
                self._support_text(item),
                self._condition_text(item),
            )
        ).casefold()
        return self._search in haystack

    def _sort_key(self, item: InventoryItem):
        staged = self._staged_counts.get(item.handle)
        count = staged if staged is not None else item.count
        position = (
            item.y is None,
            item.y if item.y is not None else 0,
            item.x if item.x is not None else 0,
        )
        if item.width is None or item.height is None:
            size = (True, 0, 0, 0)
        else:
            size = (False, item.width * item.height, item.width, item.height)
        effective_weight = (
            staged * item.unit_weight
            if staged is not None and item.unit_weight is not None
            else item.total_weight
        )
        staged_condition = self._staged_durability.get(item.handle)
        effective_condition = (
            staged_condition if staged_condition is not None else item.condition
        )
        values = {
            self.NAME_COLUMN: self._display_name(item).casefold(),
            self.CATEGORY_COLUMN: self.category_text(item).casefold(),
            self.POSITION_COLUMN: position,
            self.SIZE_COLUMN: size,
            self.TYPE_KEY_COLUMN: item.type_key.casefold(),
            self.COUNT_COLUMN: (count is None, count if count is not None else 0),
            self.WEIGHT_COLUMN: (
                effective_weight is None,
                effective_weight if effective_weight is not None else 0.0,
            ),
            self.CONDITION_COLUMN: (
                effective_condition is None,
                effective_condition if effective_condition is not None else 0.0,
            ),
            self.SUPPORT_COLUMN: self._support_text(item).casefold(),
            self.HANDLE_COLUMN: item.handle,
        }
        return (values.get(self._sort_column, ""), item.handle)

    def _position_text(self, item: InventoryItem) -> str:
        staged = self._staged_placements.get(item.handle)
        if staged is not None:
            placement_type, slot_id = staged
            if placement_type == "slot" and slot_id is not None:
                return f"экипировано (слот {slot_id})"
            return {"belt": "пояс", "ruck": "рюкзак"}.get(
                placement_type,
                item.position,
            )
        return item.position

    @staticmethod
    def _normalise_absent(text: str) -> str:
        return "—" if text == "неизвестно" else text

    def _display_value(self, item: InventoryItem, column: int) -> str:
        staged = self._staged_counts.get(item.handle)
        if column == self.NAME_COLUMN:
            return self._display_name(item)
        if column == self.CATEGORY_COLUMN:
            return self.category_text(item)
        if column == self.POSITION_COLUMN:
            return self._normalise_absent(self._position_text(item))
        if column == self.SIZE_COLUMN:
            return self._normalise_absent(item.size_text)
        if column == self.TYPE_KEY_COLUMN:
            return item.type_key if item.display_name is not None else f"0x{item.type_key}"
        if column == self.COUNT_COLUMN:
            if item.count is None:
                return "—"
            return str(item.count) if staged is None else f"{item.count} → {staged}"
        if column == self.WEIGHT_COLUMN:
            if item.total_weight is None:
                return "—"
            if staged is None or item.unit_weight is None:
                return f"{item.total_weight:.1f}"
            return f"{item.total_weight:.1f} → {staged * item.unit_weight:.1f}"
        if column == self.CONDITION_COLUMN:
            staged_condition = self._staged_durability.get(item.handle)
            if item.condition is None:
                return "—"
            current = f"{item.condition * 100.0:.1f}%"
            return (
                current
                if staged_condition is None
                else f"{current} → {staged_condition * 100.0:.1f}%"
            )
        if column == self.SUPPORT_COLUMN:
            return self._support_text(item)
        if column == self.HANDLE_COLUMN:
            return item.handle_hex
        return ""

    def _tooltip(self, item: InventoryItem, column: int) -> str:
        if column == self.NAME_COLUMN:
            display_name = self._display_name(item)
            label = (
                "Название предмета взято из каталога."
                if self._name_provider is not None and display_name != item.display_name
                else "Название предмета из сохранения."
                if item.display_name is not None
                else "Название предмета не определено."
            )
            return label
        if column == self.HANDLE_COLUMN:
            return ""
        if column == self.SUPPORT_COLUMN:
            return self._support_text(item)
        if column == self.CONDITION_COLUMN:
            if item.condition is None:
                return "Для этого предмета состояние не указано."
            if item.condition_editable:
                return "Состояние предмета можно изменить."
            return "Это значение нельзя изменить."
        if column == self.COUNT_COLUMN and item.count is None:
            return "Для этого предмета количество не указано."
        if column == self.WEIGHT_COLUMN and item.total_weight is None:
            return "Вес для этого предмета неизвестен."
        if column == self.SIZE_COLUMN and self._display_value(item, column) in {"—", "неизвестно"}:
            return "Размер предмета неизвестен."
        return self._display_value(item, column)

    @staticmethod
    def _support_text(item: InventoryItem) -> str:
        if item.editable_count:
            return "Количество можно изменить"
        if item.count is None:
            return "Это значение нельзя изменить."
        if item.count <= 1:
            return "Для этого предмета нельзя изменить количество."
        if item.kind_code not in EDITABLE_STACK_KIND_CODES:
            return "Это значение нельзя изменить."
        return "Количество нельзя изменить для этого предмета."

    @staticmethod
    def _condition_text(item: InventoryItem) -> str:
        if item.condition is None:
            return "неизвестно"
        return f"{item.condition * 100.0:.1f}%"

    def _display_name(self, item: InventoryItem) -> str:
        if self._name_provider is not None:
            try:
                resolved = self._name_provider(item)
            except Exception:
                resolved = None
            if resolved and str(resolved).strip():
                return str(resolved).strip()
        return item.display_name or "Неизвестный объект"


__all__ = ["InventoryTableModel"]
