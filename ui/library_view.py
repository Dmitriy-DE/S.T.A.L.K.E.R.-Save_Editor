"""Canonical Local Saves library surface."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .formatting import human_money, human_size
from .save_discovery import GAME_IDS, GAME_TITLES, SaveDiscovery, SaveSlot, _slot_family
from .style_components import TextureFrame, action_button, panel, section_header, status_chip


def _modified_text(modified_ns: int) -> str:
    try:
        value = datetime.fromtimestamp(modified_ns / 1_000_000_000)
        today = datetime.now().date()
        if value.date() == today:
            return value.strftime("Сегодня, %H:%M")
        if value.date() == today - timedelta(days=1):
            return value.strftime("Вчера, %H:%M")
        return value.strftime("%d сен, %H:%M")
    except (OverflowError, OSError, ValueError):
        return "—"


_SHELL_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "s2_shell"
_SHELL_ICONS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "shell_icons"


class LibraryView(QWidget):
    """Interactive library with the same three-region geometry as the reference."""

    open_requested = Signal(object)
    import_requested = Signal()
    refresh_requested = Signal()
    cloud_requested = Signal()
    restore_requested = Signal(object)

    _family_labels: ClassVar[dict[str, str]] = {
        "stalker2": "S.T.A.L.K.E.R. 2",
        "cop": "Call of Pripyat",
        "clear_sky": "Clear Sky",
        "soc": "Shadow of Chornobyl",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("libraryView")
        self._slots: tuple[SaveSlot, ...] = ()
        self._searched_paths: tuple[Path, ...] = ()
        self._installed_families: set[str] = set()
        self._visible_slots: list[SaveSlot] = []
        self._snapshot: Any | None = None
        self._activity_entries: list[tuple[str, str, str]] = []
        self._row_preview_icon = QIcon()
        self._build_ui()
        self._render_game_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        # The rail and inspector own their title bands in the canonical
        # composition. Keeping them inside the columns avoids a detached
        # heading row pushing those panels down by an extra 60px.
        root.setContentsMargins(0, 0, 0, 10)
        root.setSpacing(0)

        self.status_label = QLabel("Поиск стандартных каталогов…", self)
        self.status_label.setObjectName("libraryStatus")
        self.status_label.setVisible(False)
        self.error_label = QLabel("", self)
        self.error_label.setObjectName("libraryAnalysisError")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        root.addWidget(self.error_label)

        body = QHBoxLayout()
        # Keep the shell rail on the 30 px rhythm while giving the inspector
        # the wider, tighter composition used by the canonical screen.
        body.setSpacing(18)

        self.game_rail = panel(self, object_name="libraryGameRail")
        rail_layout = QVBoxLayout(self.game_rail)
        rail_layout.setContentsMargins(12, 12, 12, 12)
        rail_layout.setSpacing(8)
        rail_layout.addWidget(QLabel("ИГРЫ", self.game_rail), 0)
        rule = QFrame(self.game_rail)
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setObjectName("railRule")
        rail_layout.addWidget(rule)
        self.game_list = QListWidget(self.game_rail)
        self.game_list.setObjectName("libraryGameList")
        self.game_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.game_list.setWordWrap(True)
        self.game_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.game_list.currentRowChanged.connect(self._render_saves)
        rail_layout.addWidget(self.game_list, 1)
        self.zone_panel = TextureFrame(self.game_rail, asset="rail_zone.png")
        self.zone_panel.setObjectName("zoneDecoration")
        self.zone_panel.setFixedHeight(340)
        zone_layout = QVBoxLayout(self.zone_panel)
        zone_layout.setContentsMargins(12, 20, 12, 12)
        zone_layout.addStretch(1)
        zone_label = QLabel("ОДНИ СОХРАНЯЮТ ИГРЫ.\nМЫ СОХРАНЯЕМ\nИСТОРИЮ.", self.zone_panel)
        zone_label.setObjectName("zoneDecorationText")
        zone_label.setWordWrap(True)
        zone_layout.addWidget(zone_label)
        rail_layout.addWidget(self.zone_panel, 1)
        # Give the rail the same visual weight as the canonical reference.
        # Stretch-only columns collapse it at review width and leave an
        # unstructured dead zone in the centre.
        self.game_rail.setFixedWidth(246)
        body.addWidget(self.game_rail, 0)
        body.addSpacing(12)

        centre = QFrame(self)
        centre.setObjectName("libraryCentre")
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(0, 0, 0, 0)
        centre_layout.setSpacing(0)
        centre_heading = QLabel("СОХРАНЕНИЯ", centre)
        centre_heading.setObjectName("screenTitle")
        centre_heading.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        centre_heading.setFixedHeight(60)
        centre_layout.addWidget(centre_heading)
        controls = QHBoxLayout()
        self.search_edit = QLineEdit(centre)
        self.search_edit.setObjectName("referenceSearch")
        self.search_edit.setMinimumHeight(39)
        self.search_edit.setPlaceholderText("Поиск по названию, категории, type-key, handle…")
        self.search_edit.textChanged.connect(lambda _value: self._render_saves(self.game_list.currentRow()))
        controls.addWidget(self.search_edit, 1)
        self.sort_combo = QComboBox(centre)
        self.sort_combo.setObjectName("referenceSort")
        self.sort_combo.setMinimumHeight(39)
        self.sort_combo.addItem("Сначала новые", "newest")
        self.sort_combo.addItem("Сначала старые", "oldest")
        self.sort_combo.currentIndexChanged.connect(lambda _index: self._render_saves(self.game_list.currentRow()))
        controls.addWidget(self.sort_combo)
        centre_layout.addLayout(controls)
        centre_layout.addSpacing(14)

        self.save_table = QTableWidget(0, 5, centre)
        self.save_table.setObjectName("librarySaveTable")
        self.save_table.setHorizontalHeaderLabels(("НАЗВАНИЕ", "ИГРА", "ДАТА И ВРЕМЯ", "РАЗМЕР", "СТАТУС"))
        self.save_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.save_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.save_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.save_table.setAlternatingRowColors(True)
        self.save_table.verticalHeader().setVisible(False)
        self.save_table.setIconSize(QSize(84, 50))
        header = self.save_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.resizeSection(0, 315)
        header.resizeSection(1, 140)
        header.resizeSection(2, 140)
        header.resizeSection(3, 88)
        self.save_table.itemSelectionChanged.connect(self._update_preview)
        self.save_table.cellDoubleClicked.connect(lambda row, _column: self._open_row(row))
        centre_layout.addWidget(self.save_table, 1)
        centre_layout.addSpacing(24)

        self.recent_activity = panel(centre, object_name="libraryRecentActivity")
        self.recent_activity.setFixedHeight(150)
        activity_layout = QVBoxLayout(self.recent_activity)
        activity_layout.setContentsMargins(10, 8, 10, 8)
        activity_layout.addWidget(section_header("НЕДАВНЯЯ АКТИВНОСТЬ", "ПРОВЕРКА ИСТОРИИ", self.recent_activity))
        self.activity_table = QTableWidget(0, 3, self.recent_activity)
        self.activity_table.setObjectName("libraryActivityTable")
        self.activity_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.activity_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.horizontalHeader().setVisible(False)
        self.activity_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.activity_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.activity_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.activity_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        activity_layout.addWidget(self.activity_table, 1)
        self.activity_label = QLabel("Нет операций в текущем сеансе", self.recent_activity)
        self.activity_label.setObjectName("libraryActivityText")
        self.activity_label.setVisible(False)
        centre_layout.addWidget(self.recent_activity, 0)
        body.addWidget(centre, 1)

        self.preview_panel = panel(self, object_name="libraryPreviewPanel")
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(18, 0, 0, 0)
        preview_layout.setSpacing(5)
        preview_heading = section_header("ПРОСМОТР СОХРАНЕНИЯ", parent=self.preview_panel)
        preview_heading.setFixedHeight(52)
        preview_layout.addWidget(preview_heading)
        self.preview_image = QLabel("ЗОНА\nПОМНИ\nВСЁ", self.preview_panel)
        self.preview_image.setObjectName("libraryPreviewImage")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setFixedHeight(144)
        preview_pixmap = QPixmap(str(_SHELL_ASSETS / "preview_zone.png"))
        if not preview_pixmap.isNull():
            self._row_preview_icon = QIcon(preview_pixmap)
            self.preview_image.setPixmap(preview_pixmap)
            self.preview_image.setScaledContents(True)
            self.preview_image.setToolTip("Декоративное изображение зоны; thumbnail сейва не заявлен.")
        preview_layout.addWidget(self.preview_image)
        self.preview_name = QLabel("Сохранение не выбрано", self.preview_panel)
        self.preview_name.setObjectName("libraryPreviewName")
        self.preview_name.setWordWrap(True)
        preview_layout.addWidget(self.preview_name)
        self.preview_meta = QLabel("Выбери строку, чтобы увидеть источник и целостность.", self.preview_panel)
        self.preview_meta.setObjectName("libraryPreviewMeta")
        self.preview_meta.setWordWrap(True)
        preview_layout.addWidget(self.preview_meta)
        self.preview_status = status_chip("ОЖИДАЕТ АНАЛИЗА", self.preview_panel, tone="neutral")
        preview_layout.addWidget(self.preview_status, 0, Qt.AlignmentFlag.AlignLeft)
        self.capability_row = QGridLayout()
        self.capability_row.setHorizontalSpacing(5)
        self.capability_row.setVerticalSpacing(5)
        self.preview_editable_chip = status_chip("АНАЛИЗ ПО ЗАПРОСУ", self.preview_panel, tone="neutral")
        self.preview_local_chip = status_chip("ЛОКАЛЬНЫЙ", self.preview_panel, tone="neutral")
        self.preview_integrity_chip = status_chip("CRC НЕ ПРОВЕРЕН", self.preview_panel, tone="neutral")
        self.preview_inventory_chip = status_chip("ИНВЕНТАРЬ —", self.preview_panel, tone="neutral")
        self.capability_row.addWidget(self.preview_editable_chip, 0, 0)
        self.capability_row.addWidget(self.preview_local_chip, 0, 1)
        self.capability_row.addWidget(self.preview_integrity_chip, 1, 0)
        self.capability_row.addWidget(self.preview_inventory_chip, 1, 1)
        preview_layout.addLayout(self.capability_row)
        self.quick_summary = panel(self.preview_panel, object_name="libraryQuickSummary")
        summary_layout = QGridLayout(self.quick_summary)
        summary_layout.setContentsMargins(8, 7, 8, 7)
        summary_layout.setHorizontalSpacing(16)
        summary_layout.setVerticalSpacing(5)
        self.money_summary = QLabel("ДЕНЬГИ\n—", self.quick_summary)
        self.items_summary = QLabel("ПРЕДМЕТЫ\n—", self.quick_summary)
        self.equipment_summary = QLabel("СНАРЯЖЕНИЕ\n—", self.quick_summary)
        self.condition_summary = QLabel("ПРОЧНОСТЬ\n—", self.quick_summary)
        for index, label in enumerate(
            (
                self.money_summary,
                self.items_summary,
                self.equipment_summary,
                self.condition_summary,
            )
        ):
            label.setObjectName("librarySummaryValue")
            label.setWordWrap(True)
            summary_layout.addWidget(label, index // 2, index % 2)
        preview_layout.addWidget(self.quick_summary)
        preview_layout.addStretch(1)
        self.open_button = action_button("ОТКРЫТЬ СОХРАНЕНИЕ  →", self.preview_panel, kind="primary", object_name="primaryActionButton")
        self.open_button.setFixedHeight(48)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_selected)
        preview_layout.addWidget(self.open_button)
        buttons = QHBoxLayout()
        self.import_button = action_button("ИМПОРТИРОВАТЬ…", self.preview_panel)
        self.import_button.clicked.connect(self.import_requested)
        self.refresh_button = action_button("ОБНОВИТЬ", self.preview_panel)
        self.refresh_button.clicked.connect(self.refresh_requested)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.refresh_button)
        self.import_button.setFixedHeight(36)
        self.refresh_button.setFixedHeight(36)
        preview_layout.addLayout(buttons)
        self.restore_button = action_button("ВОССТАНОВИТЬ КОПИЮ", self.preview_panel)
        self.restore_button.setFixedHeight(38)
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self.restore_selected)
        preview_layout.addWidget(self.restore_button)
        self.preview_panel.setFixedWidth(380)
        body.addWidget(self.preview_panel, 0)
        root.addLayout(body, 1)

    def set_installed_families(self, families: Iterable[str]) -> None:
        self._installed_families = set(families)
        self._render_game_list()

    def set_discovery(self, discovery: SaveDiscovery) -> None:
        self._slots = tuple(discovery.slots)
        self._searched_paths = tuple(discovery.searched_paths)
        self.status_label.setText(f"Найдено сохранений: {len(self._slots)}  ·  каталогов: {len(self._searched_paths)}")
        self._render_game_list()

    def set_error(self, message: str) -> None:
        self.status_label.setText(f"Поиск не выполнен: {message}")
        self.preview_status.setText("ОШИБКА ПОИСКА")
        self.preview_status.setProperty("tone", "danger")
        self.preview_status.style().unpolish(self.preview_status)
        self.preview_status.style().polish(self.preview_status)
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))

    def set_analysis_state(self, message: str) -> None:
        self.status_label.setText(message)
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.preview_name.setText("Открытие сохранения…")
        self.preview_meta.setText("Идёт проверка bytes. Редактор откроется только после успешного анализа.")
        self.preview_status.setText("ПРОВЕРКА")
        self.preview_status.setProperty("tone", "warning")
        self.preview_status.style().unpolish(self.preview_status)
        self.preview_status.style().polish(self.preview_status)
        self.open_button.setEnabled(False)
        self.preview_integrity_chip.setText("CRC ПРОВЕРЯЕТСЯ")
        self.preview_inventory_chip.setText("ИНВЕНТАРЬ ПРОВЕРЯЕТСЯ")

    def set_analysis_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.preview_name.setText("Новый сейв не открыт")
        self.preview_meta.setText(
            "Последний корректный snapshot сохранён внутри приложения и не выдан за результат этой попытки.\n"
            f"Причина: {message}"
        )
        self.preview_status.setText("ОШИБКА АНАЛИЗА")
        self.preview_status.setProperty("tone", "danger")
        self.preview_status.style().unpolish(self.preview_status)
        self.preview_status.style().polish(self.preview_status)
        self.open_button.setEnabled(False)
        self.preview_integrity_chip.setText("CRC НЕ ПРОВЕРЕН")
        self.preview_inventory_chip.setText("ИНВЕНТАРЬ НЕ ПРОЧИТАН")

    def set_snapshot(self, snapshot: Any | None) -> None:
        """Refresh the selected-save detail from an already verified snapshot."""

        self._snapshot = snapshot
        if snapshot is None:
            return
        info = snapshot.info
        self.preview_status.setText("ПРОВЕРЕНО")
        self.preview_status.setProperty("tone", "success")
        self.preview_status.style().unpolish(self.preview_status)
        self.preview_status.style().polish(self.preview_status)
        capabilities = getattr(snapshot, "capabilities", None)
        editable = bool(
            capabilities is not None
            and any(
                capabilities.support(name).writable
                for name in ("edit_money", "edit_stacks", "edit_durability")
            )
        )
        self.preview_editable_chip.setText("РЕДАКТИРУЕМЫЙ" if editable else "READ-ONLY")
        self.preview_editable_chip.setProperty("tone", "success" if editable else "neutral")
        self.preview_editable_chip.style().unpolish(self.preview_editable_chip)
        self.preview_editable_chip.style().polish(self.preview_editable_chip)
        money = human_money(info.money) if info.money is not None else "—"
        self.money_summary.setText(f"ДЕНЬГИ\n{money} ₽")
        self.items_summary.setText(f"ПРЕДМЕТЫ\n{len(info.inventory)}")
        equipment_count = sum(
            1
            for item in info.inventory
            if item.category not in {"ammo", "consumable", "artifact", "quest", "module"}
        )
        conditions = tuple(
            float(item.condition) * 100.0
            for item in info.inventory
            if item.condition is not None
        )
        average_condition = (
            f"{sum(conditions) / len(conditions):.0f}% (средняя)"
            if conditions
            else "—"
        )
        self.equipment_summary.setText(f"СНАРЯЖЕНИЕ\n{equipment_count} комплектов")
        self.condition_summary.setText(f"ПРОЧНОСТЬ\n{average_condition}")
        self.preview_integrity_chip.setText("CRC PASS" if info.crc_ok else "CRC ПРОВЕРИТЬ")
        self.preview_inventory_chip.setText(f"ИНВЕНТАРЬ · {len(info.inventory)}")

    def set_recent_activity(self, entries: Iterable[tuple[str, str, str]]) -> None:
        """Render only operations supplied by the current session or journal."""

        self._activity_entries = list(entries)[-4:]
        if not self._activity_entries:
            self.activity_label.setText("Нет подтверждённых операций в текущем сеансе")
            self.activity_table.setRowCount(0)
            return
        visible = tuple(reversed(self._activity_entries))
        self.activity_label.setText("\n".join(f"{label} · {target} · {status}" for label, target, status in visible))
        self.activity_table.setRowCount(0)
        for row, (label, target, status) in enumerate(visible):
            self.activity_table.insertRow(row)
            for column, value in enumerate((label, target, status)):
                item = QTableWidgetItem(value)
                if column == 0 and not self._row_preview_icon.isNull():
                    item.setIcon(self._row_preview_icon)
                self.activity_table.setItem(row, column, item)
            self.activity_table.setRowHeight(row, 31)

    def append_recent_activity(self, label: str, target: str, status: str) -> None:
        self.set_recent_activity((*self._activity_entries, (label, target, status)))

    def set_recent_activity_from_snapshot(self, snapshot: Any, *, operation: str) -> None:
        """Record a fact from a newly inspected snapshot without fabricating metadata."""

        self.append_recent_activity(
            operation,
            str(getattr(snapshot, "path", "—")),
            f"SHA {snapshot.info.sha256[:12]}…",
        )

    def _family_slots(self, family: str | None) -> list[SaveSlot]:
        slots = [slot for slot in self._slots if family is None or _slot_family(slot) == family]
        query = self.search_edit.text().strip().casefold()
        if query:
            slots = [slot for slot in slots if query in f"{slot.path.name} {slot.game_title} {slot.status_text}".casefold()]
        reverse = self.sort_combo.currentData() != "oldest"
        return sorted(slots, key=lambda slot: slot.modified_ns, reverse=reverse)

    def _render_game_list(self) -> None:
        previous = self.game_list.currentRow()
        self.game_list.blockSignals(True)
        self.game_list.clear()
        all_item = QListWidgetItem(f"ВСЕ ИГРЫ\n{len(self._slots)} сохранений")
        all_icon = QIcon(str(_SHELL_ICONS / "library.svg"))
        if not all_icon.isNull():
            all_item.setIcon(all_icon)
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.game_list.addItem(all_item)
        for family in GAME_IDS:
            count = len([slot for slot in self._slots if _slot_family(slot) == family])
            label = self._family_labels.get(family, GAME_TITLES.get(family, family))
            item = QListWidgetItem(f"{label}\n{count} сохранений")
            family_icon = QIcon(str(_SHELL_ICONS / ("cloud.svg" if family == "stalker2" else "history.svg")))
            if not family_icon.isNull():
                item.setIcon(family_icon)
            item.setData(Qt.ItemDataRole.UserRole, family)
            item.setSizeHint(QSize(0, 52))
            self.game_list.addItem(item)
        row = previous if 0 <= previous < self.game_list.count() else 0
        self.game_list.setCurrentRow(row)
        self.game_list.blockSignals(False)
        self._render_saves(row)

    def _render_saves(self, row: int) -> None:
        if row < 0 or row >= self.game_list.count():
            return
        family = self.game_list.item(row).data(Qt.ItemDataRole.UserRole)
        family = str(family) if family is not None else None
        self._visible_slots = self._family_slots(family)
        self.save_table.setRowCount(0)
        for slot in self._visible_slots:
            table_row = self.save_table.rowCount()
            self.save_table.insertRow(table_row)
            table_game = self._family_labels.get(_slot_family(slot), slot.game_title)
            values = (
                f"{slot.path.stem}\n{slot.path.name}",
                table_game if slot.format_id else slot.candidate_game_title,
                _modified_text(slot.modified_ns),
                human_size(slot.size),
                (
                    "●  Готово     Редактируемый"
                    if slot.format_id is not None
                    else slot.status_text
                ),
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, str(slot.path))
                    if not self._row_preview_icon.isNull():
                        cell.setIcon(self._row_preview_icon)
                self.save_table.setItem(table_row, column, cell)
            self.save_table.setRowHeight(table_row, 64)
        if self.save_table.rowCount():
            self.save_table.selectRow(0)
        self._update_preview()

    def _selected_slot(self) -> SaveSlot | None:
        selected = self.save_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        return self._visible_slots[row] if 0 <= row < len(self._visible_slots) else None

    def _update_preview(self) -> None:
        slot = self._selected_slot()
        self.open_button.setEnabled(slot is not None)
        self.restore_button.setEnabled(slot is not None)
        if slot is None:
            self.preview_name.setText("Сохранение не выбрано")
            self.preview_meta.setText("Выбери строку, чтобы увидеть источник и целостность.")
            self.preview_status.setText("ОЖИДАЕТ АНАЛИЗА")
            return
        self.preview_name.setText(slot.path.name)
        self.preview_meta.setText(
            f"Игра: {slot.game_title or slot.candidate_game_title}\n"
            f"Источник: локальное сохранение\n"
            f"Дата: {_modified_text(slot.modified_ns)}\n"
            f"Размер: {human_size(slot.size)}"
        )
        self.preview_status.setText("ГОТОВО · АНАЛИЗ ПО ЗАПРОСУ")

    def _open_row(self, row: int) -> None:
        if 0 <= row < len(self._visible_slots):
            self.open_requested.emit(Path(self._visible_slots[row].path))

    def open_selected(self) -> None:
        slot = self._selected_slot()
        if slot is not None:
            self.open_requested.emit(Path(slot.path))

    def restore_selected(self) -> None:
        slot = self._selected_slot()
        if slot is not None:
            self.restore_requested.emit(Path(slot.path))


__all__ = ["LibraryView"]
