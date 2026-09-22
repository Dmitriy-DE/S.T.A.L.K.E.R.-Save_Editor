"""Dedicated Equipment editor surface for the Qt shell."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from PySide6.QtCore import QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from editor.catalog import ItemCatalog
from editor.equipment import EquipmentItem, helmet_category_supported

from .equipment_model import EquipmentTableModel
from .inventory_view import _donor_resolver_for
from .xray_assets import XRayIconResolver


class EquipmentView(QWidget):
    """Filterable equipment table with immutable repair staging signals."""

    repair_requested = Signal(int, float)
    reset_requested = Signal(int)
    bulk_repair_requested = Signal(str, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = EquipmentTableModel(self)
        self.table = QTableView(self)
        self.selected_handle: int | None = None
        self._items: tuple[EquipmentItem, ...] = ()
        self._staged: dict[int, float] = {}
        self._release_id: str | None = None
        self._resolver = XRayIconResolver(None)
        self._build_ui()
        self.set_release(None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по названию, категории, type-key, handle…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.model.set_search)
        filters.addWidget(self.search_edit, 2)
        self.filter_combo = QComboBox()
        for label, value in (
            ("Все", "all"),
            ("Оружие", "weapon"),
            ("Броня", "armor"),
            ("Шлемы", "helmet"),
            ("Модули", "module"),
            ("Устройства", "device"),
            ("Расходники", "consumable"),
            ("Боеприпасы", "ammo"),
            ("Артефакты", "artifact"),
            ("Квестовые предметы", "quest"),
            ("Экипировано", "equipped"),
            ("Рюкзак", "inventory"),
            ("Повреждено", "damaged"),
            ("Изменённое", "staged"),
        ):
            self.filter_combo.addItem(label, value)
        self.filter_combo.currentIndexChanged.connect(
            lambda _index: self.model.set_filter(str(self.filter_combo.currentData()))
        )
        filters.addWidget(self.filter_combo, 1)
        layout.addLayout(filters)

        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setIconSize(QSize(30, 30))
        self.table.setSortingEnabled(True)
        self.table.setMinimumWidth(850)
        self.table.setMinimumHeight(260)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in {
            EquipmentTableModel.NAME_COLUMN: 280,
            EquipmentTableModel.CATEGORY_COLUMN: 110,
            EquipmentTableModel.LOCATION_COLUMN: 130,
            EquipmentTableModel.CONDITION_COLUMN: 110,
            EquipmentTableModel.SUPPORT_COLUMN: 150,
            EquipmentTableModel.UPGRADES_COLUMN: 180,
            EquipmentTableModel.HANDLE_COLUMN: 125,
        }.items():
            header.resizeSection(column, width)
        self.table.selectionModel().currentRowChanged.connect(self._on_current_row_changed)
        layout.addWidget(self.table, 1)

        editor = QGroupBox("Редактор оборудования")
        editor_layout = QVBoxLayout(editor)
        self.selected_label = QLabel("Строка не выбрана")
        self.selected_label.setWordWrap(True)
        editor_layout.addWidget(self.selected_label)

        repair_row = QHBoxLayout()
        self.percent_spin = QDoubleSpinBox()
        self.percent_spin.setRange(0.0, 100.0)
        self.percent_spin.setDecimals(1)
        self.percent_spin.setSingleStep(1.0)
        self.percent_spin.setSuffix(" %")
        self.percent_spin.setValue(100.0)
        repair_row.addWidget(QLabel("Новое состояние"))
        repair_row.addWidget(self.percent_spin)
        self.repair_button = QPushButton("Отремонтировать")
        self.repair_button.clicked.connect(self._repair_selected)
        repair_row.addWidget(self.repair_button)
        self.repair_full_button = QPushButton("Ремонт до 100%")
        self.repair_full_button.clicked.connect(self._repair_full_selected)
        repair_row.addWidget(self.repair_full_button)
        self.reset_button = QPushButton("Сбросить выбранное")
        self.reset_button.clicked.connect(self._reset_selected)
        repair_row.addWidget(self.reset_button)
        editor_layout.addLayout(repair_row)

        bulk_row = QHBoxLayout()
        self.bulk_damaged_button = QPushButton("Ремонт повреждённых")
        self.bulk_equipped_button = QPushButton("Ремонт экипированных")
        self.bulk_weapon_button = QPushButton("Ремонт оружия")
        self.bulk_armor_button = QPushButton("Ремонт брони")
        self.bulk_helmet_button = QPushButton("Ремонт шлемов")
        for button, value in (
            (self.bulk_damaged_button, "damaged"),
            (self.bulk_equipped_button, "equipped"),
            (self.bulk_weapon_button, "weapon"),
            (self.bulk_armor_button, "armor"),
            (self.bulk_helmet_button, "helmet"),
        ):
            button.clicked.connect(
                lambda _checked=False, filter_name=value: self._repair_bulk(filter_name)
            )
            bulk_row.addWidget(button)
        editor_layout.addLayout(bulk_row)
        self.status_label = QLabel(
            "Выбери weapon, armor или helmet. Неизвестные и неподтверждённые поля остаются read-only."
        )
        self.status_label.setWordWrap(True)
        editor_layout.addWidget(self.status_label)
        layout.addWidget(editor)
        self._update_actions(None)

    def set_release(self, release_id: str | None) -> None:
        """Expose the helmet filter only for releases with separate helmets."""

        self._release_id = release_id
        supported = release_id is not None and helmet_category_supported(release_id)
        helmet_index = self.filter_combo.findData("helmet")
        if helmet_index >= 0:
            popup = self.filter_combo.view()
            if isinstance(popup, QListView):
                popup.setRowHidden(helmet_index, not supported)
            model = self.filter_combo.model()
            item = model.item(helmet_index) if isinstance(model, QStandardItemModel) else None
            if item is not None:
                item.setEnabled(supported)
            if not supported and self.filter_combo.currentData() == "helmet":
                self.filter_combo.setCurrentIndex(0)
        self.bulk_helmet_button.setVisible(supported)
        self._update_actions(self._selected_item())

    def set_items(self, items: Iterable[EquipmentItem]) -> None:
        self._items = tuple(items)
        self._staged = {}
        self.model.set_items(self._items)
        self.search_edit.clear()
        self.filter_combo.setCurrentIndex(0)
        self.selected_handle = None
        self.table.clearSelection()
        self._update_actions(None)

    def set_catalog(self, catalog: ItemCatalog | None) -> None:
        self._resolver = XRayIconResolver(catalog, donor=_donor_resolver_for(catalog))
        self.model.set_icon_provider(self._icon_for_item)

    def set_staged_durability(self, values: Mapping[int, float]) -> None:
        self._staged = {int(handle): float(value) for handle, value in values.items()}
        self.model.set_staged(self._staged)
        self._update_actions(self._selected_item())

    def show_repair_result(self, message: str) -> None:
        self.status_label.setText(message)

    def _icon_for_item(self, item: EquipmentItem):
        category = (
            "outfit"
            if item.category in {"armor", "helmet"}
            else item.category
            if item.category in {
                "weapon",
                "module",
                "device",
                "consumable",
                "ammo",
                "artifact",
                "quest",
            }
            else "other"
        )
        return self._resolver.icon_for_item(
            item.type_key,
            item.name,
            category,
            size=30,
        )

    def _selected_item(self) -> EquipmentItem | None:
        if self.selected_handle is None:
            return None
        return next((item for item in self._items if item.handle == self.selected_handle), None)

    def _on_current_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        item = self.model.item_at(current.row()) if current.isValid() else None
        self.selected_handle = item.handle if item is not None else None
        self._update_actions(item)

    def _update_actions(self, item: EquipmentItem | None) -> None:
        writable = item is not None and item.durability_editable
        self.repair_button.setEnabled(writable)
        self.repair_full_button.setEnabled(writable)
        self.reset_button.setEnabled(item is not None and item.handle in self._staged)
        bulk_buttons = {
            "damaged": self.bulk_damaged_button,
            "equipped": self.bulk_equipped_button,
            "weapon": self.bulk_weapon_button,
            "armor": self.bulk_armor_button,
            "helmet": self.bulk_helmet_button,
        }
        for filter_name, button in bulk_buttons.items():
            button.setEnabled(
                any(
                    candidate.durability_editable
                    and self._matches_bulk_filter(candidate, filter_name)
                    for candidate in self._items
                )
            )
        if item is None:
            self.selected_label.setText("Строка не выбрана")
            self.status_label.setText(
                f"Выбери weapon, armor{', helmet' if self._release_id and helmet_category_supported(self._release_id) else ''}. "
                "Неизвестные и неподтверждённые поля остаются read-only."
            )
            return
        effective = self._staged.get(item.handle, item.condition)
        current = "—" if effective is None else f"{effective * 100.0:.1f}%"
        self.selected_label.setText(
            f"{item.name} · {item.category} · {item.location} · прочность {current}"
        )
        if writable:
            self.status_label.setText(
                "Экспериментально: staged до preview; исходный сейв не изменяется."
                if item.durability.maturity == "experimental"
                else "Проверено: staged до preview; исходный сейв не изменяется."
            )
        else:
            reason = item.durability.reason or "writer недоступен"
            self.status_label.setText(
                f"Только чтение ({item.durability.maturity}): {reason}"
            )

    @staticmethod
    def _matches_bulk_filter(item: EquipmentItem, filter_name: str) -> bool:
        if filter_name == "damaged":
            return item.damaged
        if filter_name == "equipped":
            return item.location == "equipped"
        return item.category == filter_name

    def _repair_selected(self) -> None:
        if self.selected_handle is not None:
            self.repair_requested.emit(self.selected_handle, self.percent_spin.value())

    def _repair_full_selected(self) -> None:
        if self.selected_handle is not None:
            self.repair_requested.emit(self.selected_handle, 100.0)

    def _reset_selected(self) -> None:
        if self.selected_handle is not None:
            self.reset_requested.emit(self.selected_handle)

    def _repair_bulk(self, filter_name: str) -> None:
        self.bulk_repair_requested.emit(filter_name, self.percent_spin.value())


__all__ = ["EquipmentView"]
