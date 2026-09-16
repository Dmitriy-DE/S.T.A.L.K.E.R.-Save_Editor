"""Inventory controls for the optional Qt shell."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from editor.catalog import ItemCatalog, UpgradeCatalog
from save_format import EDITABLE_STACK_KIND_CODES, InventoryItem

from .inventory_model import InventoryTableModel


class InventoryView(QWidget):
    """Searchable inventory table with local, unapplied stack staging."""

    stage_requested = Signal(int, int)
    clear_selected_requested = Signal(int)
    clear_all_requested = Signal()
    add_requested = Signal(str, int)
    remove_selected_requested = Signal(int)
    durability_stage_requested = Signal(int, float)
    durability_clear_requested = Signal(int)
    upgrades_stage_requested = Signal(int, object)
    upgrades_clear_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = InventoryTableModel(self)
        self.selected_handle: int | None = None
        self._editing_enabled = True
        self._catalog: ItemCatalog | None = None
        self._add_enabled = False
        self._add_reason: str | None = None
        self._remove_enabled = False
        self._remove_reason: str | None = None
        self._removed_handles: set[int] = set()
        self._durability_enabled = False
        self._durability_reason: str | None = None
        self._staged_counts: dict[int, int] = {}
        self._staged_durability: dict[int, float] = {}
        self._upgrade_catalog: UpgradeCatalog | None = None
        self._upgrades_enabled = False
        self._upgrades_reason: str | None = None
        self._staged_upgrades: dict[int, tuple[str, ...]] = {}
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
        self.remove_item_button = QPushButton("Удалить из инвентаря")
        self.remove_item_button.setEnabled(False)
        self.remove_item_button.clicked.connect(self._remove_selected)
        count_row.addWidget(self.remove_item_button)
        form.addRow("Новое количество", count_row)

        condition_row = QHBoxLayout()
        self.condition_spin = QDoubleSpinBox()
        self.condition_spin.setRange(0.0, 100.0)
        self.condition_spin.setDecimals(1)
        self.condition_spin.setSingleStep(1.0)
        self.condition_spin.setSuffix(" %")
        self.condition_spin.setEnabled(False)
        self.condition_spin.valueChanged.connect(self._on_condition_changed)
        condition_row.addWidget(self.condition_spin)
        self.condition_stage_button = QPushButton("Застейджить прочность")
        self.condition_stage_button.setEnabled(False)
        self.condition_stage_button.clicked.connect(self._stage_condition)
        condition_row.addWidget(self.condition_stage_button)
        self.condition_clear_button = QPushButton("Очистить прочность")
        self.condition_clear_button.setEnabled(False)
        self.condition_clear_button.clicked.connect(self._clear_condition)
        condition_row.addWidget(self.condition_clear_button)
        form.addRow("Прочность", condition_row)
        self.condition_status_label = QLabel(
            "Для оружия и экипировки с подтверждённым condition доступно изменение 0…100%."
        )
        self.condition_status_label.setWordWrap(True)
        form.addRow("Состояние", self.condition_status_label)

        upgrade_row = QVBoxLayout()
        self.upgrade_list = QListWidget()
        self.upgrade_list.setObjectName("upgradeList")
        self.upgrade_list.setMaximumHeight(150)
        self.upgrade_list.setToolTip(
            "Только официальные upgrades выбранного релиза; неизвестные уже записанные ID сохраняются."
        )
        upgrade_row.addWidget(self.upgrade_list)
        upgrade_actions = QHBoxLayout()
        self.upgrade_stage_button = QPushButton("Застейджить улучшения")
        self.upgrade_stage_button.setEnabled(False)
        self.upgrade_stage_button.clicked.connect(self._stage_upgrades)
        upgrade_actions.addWidget(self.upgrade_stage_button)
        self.upgrade_clear_button = QPushButton("Очистить улучшения")
        self.upgrade_clear_button.setEnabled(False)
        self.upgrade_clear_button.clicked.connect(self._clear_upgrades)
        upgrade_actions.addWidget(self.upgrade_clear_button)
        upgrade_row.addLayout(upgrade_actions)
        self.upgrade_status_label = QLabel(
            "Для ЧН вектора улучшений нет; для ЧС/ЗП нужен официальный каталог."
        )
        self.upgrade_status_label.setWordWrap(True)
        upgrade_row.addWidget(self.upgrade_status_label)
        form.addRow("Улучшения", upgrade_row)
        layout.addWidget(editor)

        add_box = QGroupBox("Добавить предмет из официального каталога")
        add_form = QFormLayout(add_box)
        self.catalog_status_label = QLabel(
            "Открой оригинальный игровой сейв, чтобы загрузить каталог."
        )
        self.catalog_status_label.setWordWrap(True)
        add_form.addRow("Каталог", self.catalog_status_label)
        self.add_combo = QComboBox()
        self.add_combo.setMinimumContentsLength(28)
        self.add_combo.currentIndexChanged.connect(self._on_add_selection_changed)
        add_form.addRow("Предмет", self.add_combo)
        add_row = QHBoxLayout()
        self.add_quantity_spin = QSpinBox()
        self.add_quantity_spin.setRange(1, 65535)
        self.add_quantity_spin.setEnabled(False)
        add_row.addWidget(self.add_quantity_spin)
        self.add_button = QPushButton("Застейджить добавление")
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self._stage_add)
        add_row.addWidget(self.add_button)
        add_form.addRow("Количество", add_row)
        layout.addWidget(add_box)

    def set_items(self, items: Iterable[InventoryItem]) -> None:
        values = tuple(items)
        self._staged_counts.clear()
        self._staged_durability.clear()
        self._staged_upgrades.clear()
        self.count_spin.setMaximum(max((item.count_max for item in values), default=1_000_000))
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

    def set_durability_enabled(
        self,
        enabled: bool,
        *,
        reason: str | None = None,
    ) -> None:
        self._durability_enabled = bool(enabled)
        self._durability_reason = reason
        self._update_editor(self._selected_item())

    def set_staged_durability(self, durability: Mapping[int, float]) -> None:
        self._staged_durability = {
            int(handle): float(value) for handle, value in durability.items()
        }
        self.model.set_staged_durability(self._staged_durability)
        self.model.set_changed_handles(
            set(self._staged_counts)
            | set(self._staged_durability)
            | set(self._staged_upgrades)
        )
        self._update_editor(self._selected_item())

    def set_upgrades_enabled(
        self,
        enabled: bool,
        catalog: UpgradeCatalog | None,
        *,
        reason: str | None = None,
    ) -> None:
        self._upgrades_enabled = bool(enabled)
        self._upgrade_catalog = catalog
        self._upgrades_reason = reason
        self._update_editor(self._selected_item())

    def set_staged_upgrades(
        self,
        upgrades: Mapping[int, tuple[str, ...]],
    ) -> None:
        self._staged_upgrades = {
            int(handle): tuple(str(value) for value in values)
            for handle, values in upgrades.items()
        }
        self.model.set_changed_handles(
            set(self._staged_counts)
            | set(self._staged_durability)
            | set(self._staged_upgrades)
        )
        self._update_editor(self._selected_item())

    def set_catalog(
        self,
        catalog: ItemCatalog | None,
        *,
        enabled: bool,
        reason: str | None = None,
    ) -> None:
        """Expose only definitions proven for the selected release."""

        self._catalog = catalog
        self._add_enabled = bool(enabled and catalog is not None)
        self._add_reason = reason
        self.add_combo.blockSignals(True)
        self.add_combo.clear()
        if catalog is not None:
            for definition in sorted(catalog.items, key=lambda item: item.key.casefold()):
                label = definition.display_name or definition.key
                if label != definition.key:
                    label = f"{label} · {definition.key}"
                self.add_combo.addItem(label, definition.key)
        self.add_combo.blockSignals(False)
        self.catalog_status_label.setText(
            reason
            or (
                f"Загружено определений: {len(catalog.items)}"
                if catalog is not None
                else "Официальный каталог выбранной игры не найден; добавление отключено."
            )
        )
        self._on_add_selection_changed(self.add_combo.currentIndex())

    def set_remove_enabled(self, enabled: bool, *, reason: str | None = None) -> None:
        self._remove_enabled = bool(enabled)
        self._remove_reason = reason
        self._update_remove_button(self._selected_item())

    def set_removed_handles(self, handles: Mapping[int, bool]) -> None:
        self._removed_handles = {int(handle) for handle, deep in handles.items() if deep}
        self._update_remove_button(self._selected_item())

    def set_editing_enabled(self, enabled: bool, *, reason: str | None = None) -> None:
        self._editing_enabled = bool(enabled)
        if reason is not None and not self._editing_enabled:
            self.editability_label.setText(reason)
        self._update_editor(self._selected_item())

    def set_staged_counts(self, counts: Mapping[int, int]) -> None:
        selected = self.selected_handle
        self._staged_counts = {int(handle): int(value) for handle, value in counts.items()}
        self.model.set_staged_counts(self._staged_counts)
        self.model.set_changed_handles(
            set(self._staged_counts)
            | set(self._staged_durability)
            | set(self._staged_upgrades)
        )
        self._restore_selection(selected)
        self.clear_all_button.setEnabled(bool(counts))

    def set_clear_all_enabled(self, enabled: bool) -> None:
        """Keep the global staged-clear action available for add/remove edits."""

        self.clear_all_button.setEnabled(bool(enabled))

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
        self._update_remove_button(item)
        self._update_condition_editor(item)
        self._update_upgrade_editor(item)
        if item is None:
            self.selected_label.setText("Строка не выбрана")
            self.editability_label.setText(
                "Только чтение: формат не разрешает редактирование количества"
                if not self._editing_enabled
                else "Выбери строку; неподтверждённые записи остаются read-only."
            )
            self.count_spin.blockSignals(True)
            self.count_spin.setEnabled(False)
            self.count_spin.setValue(1)
            self.count_spin.blockSignals(False)
            self.stage_button.setEnabled(False)
            self.clear_selected_button.setEnabled(False)
            return

        if not self._editing_enabled:
            self.editability_label.setText(
                "Только чтение: формат не разрешает редактирование количества"
            )
            self.count_spin.blockSignals(True)
            self.count_spin.setEnabled(False)
            self.count_spin.setValue(item.count if item.count is not None else 1)
            self.count_spin.blockSignals(False)
            self.stage_button.setEnabled(False)
            self.clear_selected_button.setEnabled(False)
            return

        staged = self.model.staged_count(item.handle)
        effective_count = staged if staged is not None else (item.count if item.count is not None else 1)
        self.selected_label.setText(
            f"{item.handle_hex} • type-key 0x{item.type_key} • "
            f"позиция {item.position} • {item.category}"
        )
        if not item.editable_count:
            if item.count is None:
                reason = "Только чтение: count не извлечён"
            elif item.count <= 1:
                reason = "Только чтение: count=1"
            elif item.kind_code not in EDITABLE_STACK_KIND_CODES:
                reason = f"Только чтение: неизвестный kind={item.kind_code}"
            else:
                reason = "Только чтение: запись не подтверждена"
            self.editability_label.setText(reason)
            self.count_spin.blockSignals(True)
            self.count_spin.setEnabled(False)
            self.count_spin.setValue(item.count if item.count is not None else 1)
            self.count_spin.blockSignals(False)
            self.stage_button.setEnabled(False)
            self.clear_selected_button.setEnabled(staged is not None)
            return

        self.editability_label.setText(
            f"Можно изменить количество: {item.count} → {effective_count} "
            f"(допустимо 1..{item.count_max}; bytes пока не изменены)"
        )
        self.count_spin.blockSignals(True)
        self.count_spin.setEnabled(True)
        self.count_spin.setValue(effective_count)
        self.count_spin.blockSignals(False)
        self.stage_button.setEnabled(True)
        self.clear_selected_button.setEnabled(staged is not None)

    def _update_condition_editor(self, item: InventoryItem | None) -> None:
        self.condition_spin.blockSignals(True)
        self.condition_stage_button.setEnabled(False)
        self.condition_clear_button.setEnabled(False)
        if item is None:
            self.condition_spin.setEnabled(False)
            self.condition_spin.setValue(0.0)
            self.condition_status_label.setText(
                self._durability_reason or "Выбери оружие или экипировку."
            )
            self.condition_spin.blockSignals(False)
            return
        if not self._durability_enabled:
            self.condition_spin.setEnabled(False)
            self.condition_spin.setValue(
                item.condition * 100.0 if item.condition is not None else 0.0
            )
            self.condition_status_label.setText(
                self._durability_reason
                or "Только чтение: правка прочности не подтверждена для этого релиза."
            )
            self.condition_spin.blockSignals(False)
            return
        if not item.condition_editable or item.condition is None:
            self.condition_spin.setEnabled(False)
            self.condition_spin.setValue(
                item.condition * 100.0 if item.condition is not None else 0.0
            )
            self.condition_status_label.setText(
                "Только чтение: condition для этого объекта не разобран."
            )
            self.condition_spin.blockSignals(False)
            return

        staged = self._staged_durability.get(item.handle)
        effective = staged if staged is not None else item.condition
        self.condition_spin.setEnabled(True)
        self.condition_spin.setValue(effective * 100.0)
        self.condition_stage_button.setEnabled(True)
        self.condition_clear_button.setEnabled(staged is not None)
        mirror = (
            "STATE f32 + UPDATE q8 + client-data mirror"
            if item.condition_editable
            else "STATE f32"
        )
        prefix = f"{self._durability_reason}; " if self._durability_reason else "Подтверждено: "
        self.condition_status_label.setText(
            f"{prefix}{mirror}; bytes пока не изменены."
        )
        self.condition_spin.blockSignals(False)

    def _on_condition_changed(self, _value: float) -> None:
        item = self._selected_item()
        self.condition_stage_button.setEnabled(
            item is not None
            and self._durability_enabled
            and item.condition_editable
            and item.condition is not None
        )

    def _stage_condition(self) -> None:
        item = self._selected_item()
        if (
            item is None
            or not self._durability_enabled
            or not item.condition_editable
            or item.condition is None
        ):
            return
        self.durability_stage_requested.emit(
            item.handle,
            self.condition_spin.value() / 100.0,
        )

    def _clear_condition(self) -> None:
        if self.selected_handle is not None:
            self.durability_clear_requested.emit(self.selected_handle)

    def _update_upgrade_editor(self, item: InventoryItem | None) -> None:
        self.upgrade_list.blockSignals(True)
        self.upgrade_list.clear()
        self.upgrade_stage_button.setEnabled(False)
        self.upgrade_clear_button.setEnabled(False)
        if item is None:
            self.upgrade_list.setEnabled(False)
            self.upgrade_status_label.setText(
                self._upgrades_reason or "Выбери оружие или экипировку."
            )
            self.upgrade_list.blockSignals(False)
            return
        if item.upgrades is None:
            self.upgrade_list.setEnabled(False)
            self.upgrade_status_label.setText(
                self._upgrades_reason
                or "Только чтение: m_upgrades отсутствует или не разобран для этого объекта."
            )
            self.upgrade_list.blockSignals(False)
            return
        if not self._upgrades_enabled or self._upgrade_catalog is None:
            self.upgrade_list.setEnabled(False)
            self.upgrade_status_label.setText(
                self._upgrades_reason
                or "Только чтение: правка улучшений не подтверждена для этого релиза."
            )
            self.upgrade_list.blockSignals(False)
            return

        definitions = self._upgrade_catalog.for_item(item.type_key)
        known = {definition.key: definition for definition in definitions}
        keys = list(item.upgrades)
        keys.extend(definition.key for definition in definitions if definition.key not in keys)
        effective = self._staged_upgrades.get(item.handle, item.upgrades)
        selected = set(effective)
        self.upgrade_list.setEnabled(True)
        for key in keys:
            definition = known.get(key)
            label = (
                definition.display_name or definition.key
                if definition is not None
                else f"Неизвестный ID · {key}"
            )
            if definition is not None and label != definition.key:
                label = f"{label} · {definition.key}"
            entry = QListWidgetItem(label)
            entry.setData(Qt.ItemDataRole.UserRole, key)
            entry.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
            )
            entry.setCheckState(
                Qt.CheckState.Checked if key in selected else Qt.CheckState.Unchecked
            )
            if definition is None:
                entry.setToolTip(
                    "ID уже записан в сейве, но отсутствует в официальном каталоге; "
                    "его можно сохранить или удалить, но нельзя добавить заново."
                )
            self.upgrade_list.addItem(entry)
        self.upgrade_stage_button.setEnabled(True)
        self.upgrade_clear_button.setEnabled(item.handle in self._staged_upgrades)
        prefix = (
            "Экспериментально: STATE m_upgrades vector; backup обязателен. "
            if self._upgrades_reason is None
            else f"{self._upgrades_reason} "
        )
        self.upgrade_status_label.setText(
            f"{prefix}Официальных вариантов для {item.type_key}: {len(definitions)}; "
            "bytes пока не изменены."
        )
        self.upgrade_list.blockSignals(False)

    def _stage_upgrades(self) -> None:
        item = self._selected_item()
        if (
            item is None
            or item.upgrades is None
            or not self._upgrades_enabled
            or self._upgrade_catalog is None
        ):
            return
        values: list[str] = []
        for index in range(self.upgrade_list.count()):
            entry = self.upgrade_list.item(index)
            if entry.checkState() == Qt.CheckState.Checked:
                values.append(str(entry.data(Qt.ItemDataRole.UserRole)))
        self.upgrades_stage_requested.emit(item.handle, tuple(values))

    def _clear_upgrades(self) -> None:
        if self.selected_handle is not None:
            self.upgrades_clear_requested.emit(self.selected_handle)

    def _update_remove_button(self, item: InventoryItem | None) -> None:
        if item is None:
            self.remove_item_button.setEnabled(False)
            self.remove_item_button.setText("Удалить из инвентаря")
            return
        if not self._remove_enabled:
            self.remove_item_button.setEnabled(False)
            self.remove_item_button.setText("Удалить из инвентаря")
            if self._remove_reason:
                self.editability_label.setText(self._remove_reason)
            return
        removed = item.handle in self._removed_handles
        self.remove_item_button.setEnabled(True)
        self.remove_item_button.setText(
            "Отменить удаление" if removed else "Удалить из инвентаря"
        )

    def _on_add_selection_changed(self, _index: int) -> None:
        enabled = self._add_enabled and self.add_combo.currentIndex() >= 0
        self.add_quantity_spin.setEnabled(enabled)
        self.add_button.setEnabled(enabled)

    def _stage_add(self) -> None:
        key = self.add_combo.currentData()
        if key is None:
            return
        self.add_requested.emit(str(key), self.add_quantity_spin.value())

    def _remove_selected(self) -> None:
        if self.selected_handle is not None and self._remove_enabled:
            self.remove_selected_requested.emit(self.selected_handle)

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
