"""Canonical Local Saves library surface."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
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

from .formatting import human_size
from .launcher_view import _slot_family
from .save_slots_view import GAME_IDS, GAME_TITLES, SaveDiscovery, SaveSlot
from .style_components import TextureFrame, action_button, panel, section_header, status_chip


def _modified_text(modified_ns: int) -> str:
    try:
        return datetime.fromtimestamp(modified_ns / 1_000_000_000).strftime("%d сен, %H:%M")
    except (OverflowError, OSError, ValueError):
        return "—"


_SHELL_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "s2_shell"


class LibraryView(QWidget):
    """Interactive library with the same three-region geometry as the reference."""

    open_requested = Signal(object)
    import_requested = Signal()
    refresh_requested = Signal()
    cloud_requested = Signal()

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
        self._build_ui()
        self._render_game_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 20, 0, 0)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title = QLabel("СОХРАНЕНИЯ", self)
        title.setObjectName("screenTitle")
        title_row.addWidget(title)
        subtitle = QLabel("Локальные слоты и импортированные копии", self)
        subtitle.setObjectName("screenSubtitle")
        title_row.addWidget(subtitle)
        title_row.addStretch(1)
        self.status_label = QLabel("Поиск стандартных каталогов…", self)
        self.status_label.setObjectName("libraryStatus")
        title_row.addWidget(self.status_label)
        root.addLayout(title_row)

        body = QHBoxLayout()
        body.setSpacing(10)

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
        self.game_list.currentRowChanged.connect(self._render_saves)
        rail_layout.addWidget(self.game_list, 1)
        self.zone_panel = TextureFrame(self.game_rail, asset="rail_zone.png")
        self.zone_panel.setObjectName("zoneDecoration")
        zone_layout = QVBoxLayout(self.zone_panel)
        zone_layout.setContentsMargins(12, 20, 12, 12)
        zone_layout.addStretch(1)
        zone_label = QLabel("ОДНИ СОХРАНЯЮТ ИГРЫ.\nМЫ СОХРАНЯЕМ\nИСТОРИЮ.", self.zone_panel)
        zone_label.setObjectName("zoneDecorationText")
        zone_label.setWordWrap(True)
        zone_layout.addWidget(zone_label)
        rail_layout.addWidget(self.zone_panel, 1)
        body.addWidget(self.game_rail, 17)

        centre = QFrame(self)
        centre.setObjectName("libraryCentre")
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(0, 0, 0, 0)
        centre_layout.setSpacing(8)
        controls = QHBoxLayout()
        self.search_edit = QLineEdit(centre)
        self.search_edit.setObjectName("referenceSearch")
        self.search_edit.setPlaceholderText("⌕  Поиск по названию, категории, type-key, handle…")
        self.search_edit.textChanged.connect(lambda _value: self._render_saves(self.game_list.currentRow()))
        controls.addWidget(self.search_edit, 1)
        self.sort_combo = QComboBox(centre)
        self.sort_combo.setObjectName("referenceSort")
        self.sort_combo.addItem("⇅  Сначала новые", "newest")
        self.sort_combo.addItem("⇅  Сначала старые", "oldest")
        self.sort_combo.currentIndexChanged.connect(lambda _index: self._render_saves(self.game_list.currentRow()))
        controls.addWidget(self.sort_combo)
        centre_layout.addLayout(controls)

        self.save_table = QTableWidget(0, 5, centre)
        self.save_table.setObjectName("librarySaveTable")
        self.save_table.setHorizontalHeaderLabels(("НАЗВАНИЕ", "ИГРА", "ДАТА И ВРЕМЯ", "РАЗМЕР", "СТАТУС"))
        self.save_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.save_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.save_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.save_table.setAlternatingRowColors(True)
        self.save_table.verticalHeader().setVisible(False)
        self.save_table.setIconSize(QSize(44, 34))
        header = self.save_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.save_table.itemSelectionChanged.connect(self._update_preview)
        self.save_table.cellDoubleClicked.connect(lambda row, _column: self._open_row(row))
        centre_layout.addWidget(self.save_table, 1)

        self.recent_activity = panel(centre, object_name="libraryRecentActivity")
        activity_layout = QVBoxLayout(self.recent_activity)
        activity_layout.setContentsMargins(10, 8, 10, 8)
        activity_layout.addWidget(section_header("НЕДАВНЯЯ АКТИВНОСТЬ", "ПРОВЕРКА ИСТОРИИ", self.recent_activity))
        self.activity_label = QLabel("Нет операций в текущем сеансе", self.recent_activity)
        self.activity_label.setObjectName("libraryActivityText")
        activity_layout.addWidget(self.activity_label)
        centre_layout.addWidget(self.recent_activity, 0)
        body.addWidget(centre, 55)

        self.preview_panel = panel(self, object_name="libraryPreviewPanel")
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)
        preview_layout.addWidget(section_header("ПРОСМОТР СОХРАНЕНИЯ", parent=self.preview_panel))
        self.preview_image = QLabel("ЗОНА\nПОМНИ\nВСЁ", self.preview_panel)
        self.preview_image.setObjectName("libraryPreviewImage")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumHeight(125)
        preview_pixmap = QPixmap(str(_SHELL_ASSETS / "preview_zone.png"))
        if not preview_pixmap.isNull():
            self.preview_image.setPixmap(preview_pixmap)
            self.preview_image.setScaledContents(True)
            self.preview_image.setToolTip("Декоративный preview зоны; thumbnail сейва не заявлен.")
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
        self.capability_row = QHBoxLayout()
        self.capability_row.setSpacing(5)
        self.preview_editable_chip = status_chip("АНАЛИЗ ПО ЗАПРОСУ", self.preview_panel, tone="neutral")
        self.preview_local_chip = status_chip("ЛОКАЛЬНЫЙ", self.preview_panel, tone="neutral")
        self.capability_row.addWidget(self.preview_editable_chip)
        self.capability_row.addWidget(self.preview_local_chip)
        self.capability_row.addStretch(1)
        preview_layout.addLayout(self.capability_row)
        self.quick_summary = panel(self.preview_panel, object_name="libraryQuickSummary")
        summary_layout = QHBoxLayout(self.quick_summary)
        summary_layout.setContentsMargins(8, 7, 8, 7)
        summary_layout.setSpacing(12)
        self.money_summary = QLabel("ДЕНЬГИ\n—", self.quick_summary)
        self.items_summary = QLabel("ПРЕДМЕТЫ\n—", self.quick_summary)
        self.equipment_summary = QLabel("ЭКИПИРОВКА\n—", self.quick_summary)
        self.condition_summary = QLabel("ПРОЧНОСТЬ\n—", self.quick_summary)
        for label in (
            self.money_summary,
            self.items_summary,
            self.equipment_summary,
            self.condition_summary,
        ):
            label.setObjectName("librarySummaryValue")
            label.setWordWrap(True)
            summary_layout.addWidget(label, 1)
        preview_layout.addWidget(self.quick_summary)
        preview_layout.addStretch(1)
        self.open_button = action_button("ОТКРЫТЬ СОХРАНЕНИЕ  →", self.preview_panel, kind="primary", object_name="primaryActionButton")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_selected)
        preview_layout.addWidget(self.open_button)
        buttons = QHBoxLayout()
        self.import_button = action_button("ИМПОРТИРОВАТЬ…", self.preview_panel)
        self.import_button.clicked.connect(self.import_requested)
        self.refresh_button = action_button("⟳  ОБНОВИТЬ", self.preview_panel)
        self.refresh_button.clicked.connect(self.refresh_requested)
        buttons.addWidget(self.import_button)
        buttons.addWidget(self.refresh_button)
        preview_layout.addLayout(buttons)
        self.restore_button = action_button("↶  ВОССТАНОВИТЬ КОПИЮ", self.preview_panel)
        self.restore_button.setEnabled(False)
        preview_layout.addWidget(self.restore_button)
        body.addWidget(self.preview_panel, 28)
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
        self.money_summary.setText(f"ДЕНЬГИ\n{info.money if info.money is not None else '—'} ₽")
        self.items_summary.setText(f"ПРЕДМЕТЫ\n{len(info.inventory)}")
        self.equipment_summary.setText("ЭКИПИРОВКА\n—")
        self.condition_summary.setText("ЦЕЛОСТНОСТЬ\nCRC PASS" if info.crc_ok else "ЦЕЛОСТНОСТЬ\nПРОВЕРИТЬ")

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
        all_item = QListWidgetItem(f"▦   ВСЕ ИГРЫ\n      {len(self._slots)} сохранений")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.game_list.addItem(all_item)
        for family in GAME_IDS:
            count = len([slot for slot in self._slots if _slot_family(slot) == family])
            label = self._family_labels.get(family, GAME_TITLES.get(family, family))
            item = QListWidgetItem(f"{label}\n      {count} сохранений")
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
            values = (
                f"▧  {slot.path.stem}\n    {slot.path.name}",
                slot.game_title if slot.format_id else slot.candidate_game_title,
                _modified_text(slot.modified_ns),
                human_size(slot.size),
                slot.status_text,
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, str(slot.path))
                self.save_table.setItem(table_row, column, cell)
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


__all__ = ["LibraryView"]
