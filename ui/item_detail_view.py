"""Capability-bound item detail panel for the canonical editor."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from editor.capabilities import FormatCapabilities
from save_format import InventoryItem

from .style_components import action_button, panel, section_header, status_chip


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
        self._staged_counts: Mapping[int, int] = {}
        self._staged_durability: Mapping[int, float] = {}
        self._removed_handles: Mapping[int, bool] = {}
        self._item_icon: QIcon | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.addWidget(section_header("РЕДАКТИРОВАНИЕ ПРЕДМЕТА", "CAPABILITY-GATED", self))

        self.status_chip = status_chip("READ-ONLY", self, tone="neutral")
        root.addWidget(self.status_chip, 0, Qt.AlignmentFlag.AlignLeft)
        self.name_label = QLabel("Предмет не выбран", self)
        self.name_label.setObjectName("detailItemName")
        root.addWidget(self.name_label)
        self.type_label = QLabel("Выбери строку инвентаря", self)
        self.type_label.setObjectName("detailItemType")
        root.addWidget(self.type_label)
        self.image_label = QLabel("▧", self)
        self.image_label.setObjectName("detailItemImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(116)
        root.addWidget(self.image_label)
        self.description_label = QLabel("Данные отображаются только из текущего snapshot.", self)
        self.description_label.setObjectName("detailDescription")
        self.description_label.setWordWrap(True)
        root.addWidget(self.description_label)

        form_panel = panel(self, object_name="detailFields")
        form = QFormLayout(form_panel)
        form.setContentsMargins(10, 10, 10, 10)
        form.setSpacing(8)
        self.count_spin = QSpinBox(form_panel)
        self.count_spin.setRange(1, 1_000_000)
        self.count_apply = QPushButton("Применить", form_panel)
        self.count_apply.clicked.connect(self._emit_count)
        self.count_spin.editingFinished.connect(self._emit_count)
        self.count_apply.setVisible(False)
        count_row = QHBoxLayout()
        count_row.addWidget(self.count_spin, 1)
        count_row.addWidget(self.count_apply)
        form.addRow("Количество", count_row)

        self.condition_spin = QDoubleSpinBox(form_panel)
        self.condition_spin.setRange(0.0, 100.0)
        self.condition_spin.setDecimals(1)
        self.condition_spin.setSuffix(" %")
        self.condition_apply = QPushButton("Применить", form_panel)
        self.condition_apply.clicked.connect(self._emit_condition)
        self.condition_spin.editingFinished.connect(self._emit_condition)
        self.condition_apply.setVisible(False)
        condition_row = QHBoxLayout()
        condition_row.addWidget(self.condition_spin, 1)
        condition_row.addWidget(self.condition_apply)
        form.addRow("Состояние", condition_row)

        self.placement_combo = QComboBox(form_panel)
        self.placement_combo.addItem("Инвентарь", ("inventory", None))
        self.placement_combo.addItem("Пояс", ("belt", None))
        self.placement_combo.addItem("Рюкзак", ("ruck", None))
        self.placement_apply = QPushButton("Применить", form_panel)
        self.placement_apply.clicked.connect(self._emit_placement)
        self.placement_combo.activated.connect(lambda _index: self._emit_placement())
        self.placement_apply.setVisible(False)
        placement_row = QHBoxLayout()
        placement_row.addWidget(self.placement_combo, 1)
        placement_row.addWidget(self.placement_apply)
        form.addRow("Размещение", placement_row)
        root.addWidget(form_panel)

        root.addWidget(QLabel("УСТАНОВЛЕННЫЕ МОДУЛИ / УЛУЧШЕНИЯ", self))
        self.upgrade_list = QListWidget(self)
        self.upgrade_list.setObjectName("detailUpgradeList")
        self.upgrade_list.setMaximumHeight(92)
        root.addWidget(self.upgrade_list)
        self.module_status = QLabel("—", self)
        self.module_status.setObjectName("detailModuleStatus")
        self.module_status.setWordWrap(True)
        root.addWidget(self.module_status)
        root.addStretch(1)

        self.save_button = action_button("СОХРАНИТЬ 0 ИЗМЕНЕНИЙ", self, kind="primary", object_name="primaryActionButton")
        self.save_button.setEnabled(False)
        root.addWidget(self.save_button)
        actions = QHBoxLayout()
        self.reset_button = action_button("↶  СБРОСИТЬ", self)
        self.reset_button.setEnabled(False)
        self.reset_button.clicked.connect(self._emit_reset)
        actions.addWidget(self.reset_button)
        self.remove_button = action_button("УДАЛИТЬ ПРЕДМЕТ", self, kind="danger")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self._emit_remove)
        actions.addWidget(self.remove_button)
        root.addLayout(actions)

    def set_item(
        self,
        item: InventoryItem | None,
        capabilities: FormatCapabilities | None,
        *,
        staged_counts: Mapping[int, int] | None = None,
        staged_durability: Mapping[int, float] | None = None,
        removed_handles: Mapping[int, bool] | None = None,
    ) -> None:
        self._item = item
        self._capabilities = capabilities
        self._staged_counts = staged_counts or {}
        self._staged_durability = staged_durability or {}
        self._removed_handles = removed_handles or {}
        self._render()

    def set_item_icon(self, icon: QIcon | None) -> None:
        self._item_icon = icon
        self._render()

    def set_change_count(self, count: int) -> None:
        self.save_button.setText(f"СОХРАНИТЬ {count} ИЗМЕНЕНИЙ")
        self.save_button.setEnabled(count > 0)

    def _render(self) -> None:
        item = self._item
        caps = self._capabilities
        if item is None:
            self.name_label.setText("Предмет не выбран")
            self.type_label.setText("Выбери строку инвентаря")
            self.description_label.setText("Данные отображаются только из текущего snapshot.")
            self.status_chip.setText("READ-ONLY")
            self.count_spin.setEnabled(False)
            self.count_apply.setEnabled(False)
            self.condition_spin.setEnabled(False)
            self.condition_apply.setEnabled(False)
            self.placement_combo.setEnabled(False)
            self.placement_apply.setEnabled(False)
            self.reset_button.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.upgrade_list.clear()
            self.module_status.setText("—")
            self.image_label.clear()
            self.image_label.setText("▧")
            return

        label = item.display_name or "Неизвестный объект"
        self.name_label.setText(label)
        self.type_label.setText(f"{item.category}  ·  {item.type_key}  ·  {item.handle_hex}")
        weight = "—" if item.total_weight is None else f"{item.total_weight:.1f} кг"
        self.description_label.setText(f"Вес: {weight}\nИсточник: {item.observation_source or 'snapshot'}")
        if self._item_icon is not None and not self._item_icon.isNull():
            self.image_label.setPixmap(self._item_icon.pixmap(180, 105))
            self.image_label.setText("")
        else:
            self.image_label.setText("▧")

        stack_support = caps.support("edit_stacks") if caps is not None else None
        condition_support = caps.support("edit_durability") if caps is not None else None
        writable_stack = bool(caps and caps.edit_stacks and item.editable_count)
        writable_condition = bool(caps and caps.edit_durability and item.condition_editable and item.condition is not None)
        experimental = any(
            support is not None and support.maturity == "experimental"
            for support in (stack_support, condition_support)
        )
        self.status_chip.setText("ЭКСПЕРИМЕНТАЛЬНО" if experimental else "ПРОВЕРЕНО" if writable_stack or writable_condition else "READ-ONLY")
        self.status_chip.setProperty("tone", "warning" if experimental else "success" if writable_stack or writable_condition else "neutral")
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)

        count = self._staged_counts.get(item.handle, item.count or 1)
        self.count_spin.blockSignals(True)
        self.count_spin.setMaximum(max(1, item.count_max))
        self.count_spin.setValue(count)
        self.count_spin.blockSignals(False)
        self.count_spin.setEnabled(writable_stack)
        self.count_apply.setEnabled(writable_stack)

        condition = self._staged_durability.get(item.handle, item.condition or 0.0)
        self.condition_spin.blockSignals(True)
        self.condition_spin.setValue(condition * 100.0)
        self.condition_spin.blockSignals(False)
        self.condition_spin.setEnabled(writable_condition)
        self.condition_apply.setEnabled(writable_condition)

        placement_writable = bool(caps and caps.edit_placement and item.placement_editable)
        self.placement_combo.setEnabled(placement_writable)
        self.placement_apply.setEnabled(placement_writable)

        self.upgrade_list.clear()
        for value in item.upgrades or item.modules or ():
            self.upgrade_list.addItem(str(value))
        self.module_status.setText(
            "Модули/улучшения показаны как read-only evidence."
            if item.upgrades or item.modules
            else "Для этого предмета модульные данные не разобраны."
        )
        self.reset_button.setEnabled(
            item.handle in self._staged_counts
            or item.handle in self._staged_durability
            or item.handle in self._removed_handles
        )
        can_remove = bool(caps and caps.remove_items and item.remove_editable)
        self.remove_button.setEnabled(can_remove)

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
