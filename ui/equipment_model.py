"""Qt table model for the shared Equipment projection."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import TypeAlias

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QIcon

from editor.equipment import EquipmentItem

from .ux_copy import technical_details

ModelIndex: TypeAlias = QModelIndex | QPersistentModelIndex
IconProvider: TypeAlias = Callable[[EquipmentItem], QIcon | None]
_EMPTY_INDEX = QModelIndex()

_CATEGORY_LABELS = {
    "weapon": "Оружие",
    "armor": "Броня",
    "helmet": "Шлем",
    "module": "Модуль",
    "device": "Устройство",
    "consumable": "Расходник",
    "ammo": "Боеприпасы",
    "artifact": "Артефакт",
    "quest": "Квестовый предмет",
    "other": "Другое",
}
_LOCATION_LABELS = {
    "equipped": "Экипировано",
    "inventory": "Рюкзак",
    "belt": "Пояс",
    "unknown": "Не определено",
}
_OBSERVATION_SOURCE_LABELS = {
    "actor_inventory": "инвентарь игрока",
    "grid": "инвентарь",
    "equipped": "экипировка",
}
_MATURITY_LABELS = {
    "unsupported": "Только просмотр",
    "research": "Исследуется",
    "experimental": "Экспериментальная функция",
    "verified": "Проверено",
}


class EquipmentTableModel(QAbstractTableModel):
    """Filterable/sortable table whose row identity is the save handle."""

    NAME_COLUMN = 0
    CATEGORY_COLUMN = 1
    LOCATION_COLUMN = 2
    CONDITION_COLUMN = 3
    SUPPORT_COLUMN = 4
    UPGRADES_COLUMN = 5
    HANDLE_COLUMN = 6

    HEADERS = (
        "Предмет",
        "Категория",
        "Где находится",
        "Прочность",
        "Поддержка",
        "Улучшения",
        "Идентификатор",
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: tuple[EquipmentItem, ...] = ()
        self._visible: tuple[EquipmentItem, ...] = ()
        self._search = ""
        self._filter = "all"
        self._staged: dict[int, float] = {}
        self._icons: IconProvider | None = None
        self._sort_column = self.HANDLE_COLUMN
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._changed_brush = QBrush(QColor("#fff2cc"))

    def source_items(self) -> tuple[EquipmentItem, ...]:
        return self._items

    def visible_items(self) -> tuple[EquipmentItem, ...]:
        return self._visible

    def item_at(self, row: int) -> EquipmentItem | None:
        return self._visible[row] if 0 <= row < len(self._visible) else None

    def set_items(self, items: Iterable[EquipmentItem]) -> None:
        self._items = tuple(items)
        self._staged = {}
        self._rebuild()

    def set_staged(self, values: Mapping[int, float]) -> None:
        self._staged = {int(handle): float(value) for handle, value in values.items()}
        self._rebuild()

    def set_icon_provider(self, provider: IconProvider | None) -> None:
        self._icons = provider
        self._rebuild()

    def set_search(self, value: str) -> None:
        normalized = str(value).strip().casefold()
        if normalized != self._search:
            self._search = normalized
            self._rebuild()

    def set_filter(self, value: str) -> None:
        normalized = str(value).strip().casefold() or "all"
        if normalized not in {
            "all",
            "weapon",
            "armor",
            "helmet",
            "module",
            "device",
            "consumable",
            "ammo",
            "artifact",
            "quest",
            "equipped",
            "inventory",
            "damaged",
            "staged",
        }:
            raise ValueError(f"unknown equipment filter: {value!r}")
        if normalized != self._filter:
            self._filter = normalized
            self._rebuild()

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        if 0 <= int(column) < len(self.HEADERS):
            self._sort_column = int(column)
            self._sort_order = Qt.SortOrder(order)
            self._rebuild()

    def rowCount(self, parent: ModelIndex = _EMPTY_INDEX) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._visible)

    def columnCount(self, parent: ModelIndex = _EMPTY_INDEX) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section] if 0 <= section < len(self.HEADERS) else None
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
        if role == Qt.ItemDataRole.DecorationRole and index.column() == self.NAME_COLUMN:
            return self._icons(item) if self._icons is not None else None
        if role == Qt.ItemDataRole.BackgroundRole and item.handle in self._staged:
            return self._changed_brush
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(item, index.column())
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(item, index.column())
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in {
            self.CONDITION_COLUMN,
            self.HANDLE_COLUMN,
        }:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def _matches(self, item: EquipmentItem) -> bool:
        if self._filter in {
            "weapon",
            "armor",
            "helmet",
            "module",
            "device",
            "consumable",
            "ammo",
            "artifact",
            "quest",
        } and item.category != self._filter:
            return False
        if self._filter == "equipped" and item.location != "equipped":
            return False
        if self._filter == "inventory" and item.location != "inventory":
            return False
        if self._filter == "damaged" and not item.damaged:
            return False
        if self._filter == "staged" and item.handle not in self._staged:
            return False
        if not self._search:
            return True
        text = " ".join(
            (
                item.name,
                item.type_key,
                item.category,
                item.location,
                item.durability.maturity,
                item.durability.reason or "",
                " ".join(item.modules or ()),
                " ".join(item.upgrades or ()),
                item.handle_hex,
            )
        ).casefold()
        return self._search in text

    def _sort_key(self, item: EquipmentItem):
        condition = self._staged.get(item.handle, item.condition)
        values = {
            self.NAME_COLUMN: item.name.casefold(),
            self.CATEGORY_COLUMN: item.category,
            self.LOCATION_COLUMN: item.location,
            self.CONDITION_COLUMN: (condition is None, condition or 0.0),
            self.SUPPORT_COLUMN: item.durability.maturity,
            self.UPGRADES_COLUMN: (
                tuple(item.modules or ()),
                tuple(item.upgrades or ()),
            ),
            self.HANDLE_COLUMN: item.handle,
        }
        return values[self._sort_column], item.handle

    def _display(self, item: EquipmentItem, column: int) -> str:
        if column == self.NAME_COLUMN:
            return item.name
        if column == self.CATEGORY_COLUMN:
            return _CATEGORY_LABELS[item.category]
        if column == self.LOCATION_COLUMN:
            return _LOCATION_LABELS[item.location]
        if column == self.CONDITION_COLUMN:
            condition = self._staged.get(item.handle, item.condition)
            if condition is None:
                return "—"
            return f"{condition * 100.0:.1f}%"
        if column == self.SUPPORT_COLUMN:
            return _MATURITY_LABELS[item.durability.maturity]
        if column == self.UPGRADES_COLUMN:
            sections: list[str] = []
            if item.modules is not None:
                module_text = ", ".join(item.modules) or "нет"
                if item.module_states and any(
                    state == "unknown" for _key, state in item.module_states
                ):
                    module_text += " (состояние не подтверждено)"
                sections.append("Модули: " + module_text)
            if item.upgrades is not None:
                upgrade_text = ", ".join(item.upgrades) or "нет"
                if item.upgrade_states and any(
                    state == "unknown" for _key, state in item.upgrade_states
                ):
                    upgrade_text += " (состояние не подтверждено)"
                sections.append("Улучшения: " + upgrade_text)
            if not sections:
                return "—"
            return "; ".join(sections)
        if column == self.HANDLE_COLUMN:
            return item.handle_hex
        return ""

    def _tooltip(self, item: EquipmentItem, column: int) -> str:
        if column == self.SUPPORT_COLUMN:
            if item.durability.maturity == "unsupported":
                return "Это значение нельзя изменить."
            return _MATURITY_LABELS[item.durability.maturity]
        if column == self.NAME_COLUMN:
            family = item.serializer_family or "не определено"
            source = _OBSERVATION_SOURCE_LABELS.get(
                item.observation_source,
                "открытое сохранение",
            )
            device = (
                f"\nУстройство: {item.device_subtype}"
                if item.device_subtype is not None
                else ""
            )
            return (
                f"Источник: {source}{device}\n"
                f"{technical_details(f'Ключ типа: {item.type_key}; семейство формата: {family}; идентификатор: {item.handle_hex}')}"
            )
        if column == self.UPGRADES_COLUMN:
            if item.modules is None and item.upgrades is None:
                return "Данные о модификациях недоступны."
            return self._display(item, column)
        if column == self.CONDITION_COLUMN and item.condition is None:
            return "Состояние предмета неизвестно."
        return self._display(item, column)

    def _rebuild(self) -> None:
        visible = [item for item in self._items if self._matches(item)]
        visible.sort(
            key=self._sort_key,
            reverse=self._sort_order == Qt.SortOrder.DescendingOrder,
        )
        self.beginResetModel()
        self._visible = tuple(visible)
        self.endResetModel()


__all__ = ["EquipmentTableModel"]
