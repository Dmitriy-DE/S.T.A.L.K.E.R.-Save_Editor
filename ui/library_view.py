"""Canonical Local Saves library surface."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
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
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.releases import release_by_id

from .formatting import human_money, human_size
from .save_discovery import GAME_IDS, GAME_TITLES, SaveDiscovery, SaveSlot, _slot_family
from .style_components import TextureFrame, action_button, panel, section_header, status_chip
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import technical_details


def _modified_text(modified_ns: int) -> str:
    try:
        value = datetime.fromtimestamp(modified_ns / 1_000_000_000)
        today = datetime.now().date()
        if value.date() == today:
            return value.strftime("Сегодня, %H:%M")
        if value.date() == today - timedelta(days=1):
            return value.strftime("Вчера, %H:%M")
        months = (
            "янв", "фев", "мар", "апр", "май", "июн",
            "июл", "авг", "сен", "окт", "ноя", "дек",
        )
        return f"{value.day:02d} {months[value.month - 1]}, {value:%H:%M}"
    except (OverflowError, OSError, ValueError):
        return "—"


_SHELL_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "s2_shell"
_SHELL_ICONS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "shell_icons"
_ROW_THUMBNAIL_ASSETS = {
    "stalker2": "preview_zone.png",
    "cop": "header_panorama.png",
    "clear_sky": "rail_zone.png",
    "soc": "header_panorama.png",
}


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
        self._activity_entries: list[tuple[str, str, str, str]] = []
        self._row_thumbnail_cache: dict[Path, QPixmap] = {}
        self._technical_details = ""
        self._details_dialog: TechnicalDetailsDialog | None = None
        self._build_ui()
        self._render_game_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        # The rail and inspector own their title bands in the canonical
        # composition. Keeping them inside the columns avoids a detached
        # heading row pushing those panels down by an extra 60px.
        root.setContentsMargins(0, 6, 0, 9)
        root.setSpacing(0)

        self.status_label = QLabel("Поиск стандартных каталогов…", self)
        self.status_label.setObjectName("libraryStatus")
        self.status_label.setVisible(False)
        self.error_label = QLabel("", self)
        self.error_label.setObjectName("libraryAnalysisError")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        error_row = QHBoxLayout()
        error_row.addWidget(self.error_label, 1)
        self.details_button = action_button("ТЕХНИЧЕСКИЕ ДЕТАЛИ", self)
        self.details_button.setObjectName("libraryTechnicalDetailsButton")
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self._show_technical_details)
        error_row.addWidget(self.details_button)
        root.addLayout(error_row)

        body = QHBoxLayout()
        # Keep the shell rail on the 30 px rhythm while giving the inspector
        # the wider, tighter composition used by the canonical screen.
        body.setSpacing(16)

        self.game_rail = panel(self, object_name="libraryGameRail")
        rail_layout = QVBoxLayout(self.game_rail)
        rail_layout.setContentsMargins(10, 21, 10, 12)
        rail_layout.setSpacing(8)
        rail_layout.addWidget(QLabel("ИГРЫ", self.game_rail), 0)
        rail_layout.addSpacing(6)
        rule = QFrame(self.game_rail)
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setObjectName("railRule")
        rail_layout.addWidget(rule)
        self.game_list = QListWidget(self.game_rail)
        self.game_list.setObjectName("libraryGameList")
        self.game_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.game_list.setIconSize(QSize(28, 28))
        self.game_list.setWordWrap(True)
        self.game_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.game_list.setSpacing(8)
        self.game_list.currentRowChanged.connect(self._render_saves)
        rail_layout.addWidget(self.game_list, 1)
        self.zone_panel = TextureFrame(
            self.game_rail,
            asset="rail_zone.png",
            overlay_alpha=0,
            image_height_ratio=0.66,
        )
        self.zone_panel.setObjectName("zoneDecoration")
        self.zone_panel.setFixedHeight(294)
        zone_layout = QVBoxLayout(self.zone_panel)
        zone_layout.setContentsMargins(26, 20, 12, 12)
        zone_layout.addStretch(1)
        zone_label = QLabel(
            "ОДНИ СОХРАНЯЮТ\nИГРЫ.\nМЫ СОХРАНЯЕМ\nИСТОРИЮ.",
            self.zone_panel,
        )
        zone_label.setObjectName("libraryZoneDecorationText")
        zone_label.setWordWrap(True)
        zone_layout.addWidget(zone_label)
        rail_layout.addWidget(self.zone_panel, 1)
        # Give the rail the same visual weight as the canonical reference.
        # Stretch-only columns collapse it at review width and leave an
        # unstructured dead zone in the centre.
        self.game_rail.setFixedWidth(260)
        body.addWidget(self.game_rail, 0)
        body.addSpacing(6)

        centre = QFrame(self)
        centre.setObjectName("libraryCentre")
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(0, 0, 0, 0)
        centre_layout.setSpacing(0)
        centre_heading = QLabel("СОХРАНЕНИЯ", centre)
        centre_heading.setObjectName("screenTitle")
        centre_heading.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        centre_heading.setFixedHeight(53)
        centre_layout.addWidget(centre_heading)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 1, 0)
        controls.setSpacing(10)
        self.search_edit = QLineEdit(centre)
        self.search_edit.setObjectName("referenceSearch")
        self.search_edit.setMinimumHeight(39)
        self.search_edit.setPlaceholderText("Поиск сохранений…")
        self.search_edit.textChanged.connect(lambda _value: self._render_saves(self.game_list.currentRow()))
        controls.addWidget(self.search_edit, 1)
        self.sort_combo = QComboBox(centre)
        self.sort_combo.setObjectName("referenceSort")
        self.sort_combo.setMinimumHeight(39)
        self.sort_combo.addItem("Сначала новые", "newest")
        self.sort_combo.addItem("Сначала старые", "oldest")
        self.sort_combo.setFixedWidth(204)
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
        self.save_table.setShowGrid(False)
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
        header.resizeSection(1, 130)
        header.resizeSection(2, 125)
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
        self.activity_table = QTableWidget(0, 4, self.recent_activity)
        self.activity_table.setObjectName("libraryActivityTable")
        self.activity_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.activity_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.activity_table.setShowGrid(False)
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.horizontalHeader().setVisible(False)
        self.activity_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.activity_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.activity_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.activity_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.activity_table.setColumnWidth(0, 170)
        self.activity_table.setColumnWidth(2, 120)
        self.activity_table.setColumnWidth(3, 174)
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
        preview_heading.setFixedHeight(45)
        preview_layout.addWidget(preview_heading)
        self.preview_scroll = QScrollArea(self.preview_panel)
        self.preview_scroll.setObjectName("libraryPreviewScroll")
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.preview_body = QWidget(self.preview_scroll)
        self.preview_body.setObjectName("libraryPreviewBody")
        preview_body_layout = QVBoxLayout(self.preview_body)
        preview_body_layout.setContentsMargins(0, 0, 5, 0)
        preview_body_layout.setSpacing(5)
        self.preview_image = QLabel("ЗОНА\nПОМНИ\nВСЁ", self.preview_body)
        self.preview_image.setObjectName("libraryPreviewImage")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setFixedHeight(140)
        preview_pixmap = QPixmap(str(_SHELL_ASSETS / "preview_zone.png"))
        if not preview_pixmap.isNull():
            self.preview_image.setPixmap(preview_pixmap)
            self.preview_image.setScaledContents(True)
            self.preview_image.setToolTip(
                "Декоративное изображение зоны; обложка сохранения недоступна."
            )
        preview_body_layout.addWidget(self.preview_image)
        self.preview_name = QLabel("Сохранение не выбрано", self.preview_body)
        self.preview_name.setObjectName("libraryPreviewName")
        self.preview_name.setWordWrap(True)
        self.preview_name.setContentsMargins(0, 8, 0, 0)
        preview_body_layout.addWidget(self.preview_name)
        self.preview_metadata = QWidget(self.preview_body)
        self.preview_metadata.setObjectName("libraryPreviewMetadata")
        metadata_layout = QGridLayout(self.preview_metadata)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.setHorizontalSpacing(8)
        metadata_layout.setVerticalSpacing(1)
        metadata_layout.setColumnMinimumWidth(0, 64)
        self.preview_game_value = QLabel("—", self.preview_metadata)
        self.preview_game_value.setWordWrap(True)
        self.preview_source_value = QLabel("Локальное сохранение", self.preview_metadata)
        self.preview_date_value = QLabel("—", self.preview_metadata)
        self.preview_size_value = QLabel("—", self.preview_metadata)
        self.preview_integrity_value = QLabel("Не проверено", self.preview_metadata)
        metadata_rows = (
            ("Игра", self.preview_game_value),
            ("Источник", self.preview_source_value),
            ("Дата", self.preview_date_value),
            ("Размер", self.preview_size_value),
            ("Проверка", self.preview_integrity_value),
        )
        for row, (caption, value) in enumerate(metadata_rows):
            label = QLabel(f"{caption}:", self.preview_metadata)
            label.setObjectName("libraryMetadataLabel")
            value.setObjectName("libraryMetadataValue")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            metadata_layout.addWidget(label, row, 0)
            metadata_layout.addWidget(value, row, 1)
            metadata_layout.setRowMinimumHeight(row, 27)
        preview_body_layout.addWidget(self.preview_metadata)
        self.preview_meta = QLabel("Выбери сохранение, чтобы увидеть подробности.", self.preview_body)
        self.preview_meta.setObjectName("libraryPreviewMeta")
        self.preview_meta.setWordWrap(True)
        self.preview_meta.setVisible(False)
        preview_body_layout.addWidget(self.preview_meta)
        self.preview_status = status_chip("НЕ ПРОВЕРЕНО", self.preview_body, tone="neutral")
        self.preview_status.setVisible(False)
        preview_body_layout.addWidget(self.preview_status, 0, Qt.AlignmentFlag.AlignLeft)
        self.capability_heading = section_header("ВОЗМОЖНОСТИ", parent=self.preview_body)
        capability_heading_layout = self.capability_heading.layout()
        if capability_heading_layout is not None:
            capability_heading_layout.setContentsMargins(8, 0, 8, 0)
        preview_body_layout.addWidget(self.capability_heading)
        self.capability_row = QGridLayout()
        self.capability_row.setHorizontalSpacing(5)
        self.capability_row.setVerticalSpacing(8)
        self.preview_editable_chip = status_chip(
            "ПРОВЕРИТСЯ ПРИ ОТКРЫТИИ", self.preview_body, tone="neutral"
        )
        self.preview_local_chip = status_chip("ЛОКАЛЬНЫЙ", self.preview_body, tone="neutral")
        self.preview_integrity_chip = status_chip("НЕ ПРОВЕРЕНО", self.preview_body, tone="neutral")
        self.preview_inventory_chip = status_chip("ИНВЕНТАРЬ —", self.preview_body, tone="neutral")
        self.capability_row.addWidget(self.preview_editable_chip, 0, 0)
        self.capability_row.addWidget(self.preview_local_chip, 0, 1)
        self.capability_row.addWidget(self.preview_integrity_chip, 1, 0)
        self.capability_row.addWidget(self.preview_inventory_chip, 1, 1)
        preview_body_layout.addSpacing(7)
        self.capability_heading.setFixedHeight(24)
        preview_body_layout.addLayout(self.capability_row)
        self.summary_heading = section_header("БЫСТРАЯ СВОДКА", parent=self.preview_body)
        summary_heading_layout = self.summary_heading.layout()
        if summary_heading_layout is not None:
            summary_heading_layout.setContentsMargins(8, 0, 8, 0)
        preview_body_layout.addSpacing(26)
        self.summary_heading.setFixedHeight(21)
        preview_body_layout.addWidget(self.summary_heading)
        self.quick_summary = panel(self.preview_body, object_name="libraryQuickSummary")
        summary_layout = QGridLayout(self.quick_summary)
        summary_layout.setContentsMargins(8, 7, 8, 7)
        summary_layout.setHorizontalSpacing(10)
        summary_layout.setVerticalSpacing(7)
        summary_specs = (
            ("currency.svg", "ДЕНЬГИ", "money_summary"),
            ("inventory.svg", "ПРЕДМЕТЫ", "items_summary"),
            ("equipment.svg", "СНАРЯЖЕНИЕ", "equipment_summary"),
            ("durability.svg", "ПРОЧНОСТЬ", "condition_summary"),
        )
        summary_values: dict[str, QLabel] = {}
        for index, (icon_name, caption, value_name) in enumerate(summary_specs):
            cell = QWidget(self.quick_summary)
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(8)
            icon = QLabel(cell)
            icon.setObjectName("librarySummaryIcon")
            icon.setFixedSize(28, 28)
            summary_icon = QIcon(str(_SHELL_ICONS / icon_name))
            if not summary_icon.isNull():
                icon.setPixmap(summary_icon.pixmap(24, 24))
            cell_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
            text_column = QVBoxLayout()
            text_column.setContentsMargins(0, 0, 0, 0)
            text_column.setSpacing(1)
            caption_label = QLabel(caption, cell)
            caption_label.setObjectName("librarySummaryCaption")
            value_label = QLabel("—", cell)
            value_label.setObjectName("librarySummaryValue")
            value_label.setWordWrap(True)
            text_column.addWidget(caption_label)
            text_column.addWidget(value_label)
            cell_layout.addLayout(text_column, 1)
            summary_layout.addWidget(cell, index // 2, index % 2)
            summary_values[value_name] = value_label
            setattr(self, value_name, value_label)
        self.money_summary = summary_values["money_summary"]
        self.items_summary = summary_values["items_summary"]
        self.equipment_summary = summary_values["equipment_summary"]
        self.condition_summary = summary_values["condition_summary"]
        self.quick_summary.setFixedHeight(111)
        preview_body_layout.addWidget(self.quick_summary)
        preview_body_layout.addStretch(1)
        self.preview_scroll.setWidget(self.preview_body)
        preview_layout.addWidget(self.preview_scroll, 1)
        self.open_button = action_button("ОТКРЫТЬ СОХРАНЕНИЕ  →", self.preview_panel, kind="primary", object_name="primaryActionButton")
        self.open_button.setFixedHeight(48)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_selected)
        preview_layout.addWidget(self.open_button)
        preview_layout.addSpacing(7)
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
        preview_layout.addSpacing(7)
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
        self._technical_details = technical_details(message)
        message = "Не удалось обновить список сохранений. Проверь выбранные папки."
        self.status_label.setText("Не удалось обновить список сохранений")
        self.status_label.setToolTip("")
        self.preview_status.setText("ОШИБКА ПОИСКА")
        self.preview_status.setProperty("tone", "danger")
        self.preview_status.style().unpolish(self.preview_status)
        self.preview_status.style().polish(self.preview_status)
        self.preview_metadata.setVisible(False)
        self.preview_meta.setVisible(bool(message))
        self.preview_status.setVisible(bool(message))
        self.preview_meta.setText(message)
        self.preview_meta.setToolTip("")
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))
        self.details_button.setVisible(bool(self._technical_details))

    def set_analysis_state(self, message: str) -> None:
        self.status_label.setText(message)
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.details_button.setVisible(False)
        self._technical_details = ""
        self.preview_name.setText("Открытие сохранения…")
        self.preview_meta.setText("Проверяем файл. Редактор откроется после успешной проверки.")
        self.preview_metadata.setVisible(False)
        self.preview_meta.setVisible(True)
        self.preview_status.setVisible(True)
        self.preview_status.setText("ПРОВЕРКА")
        self.preview_status.setProperty("tone", "warning")
        self.preview_status.style().unpolish(self.preview_status)
        self.preview_status.style().polish(self.preview_status)
        self.open_button.setEnabled(False)
        self.preview_integrity_chip.setText("ПРОВЕРКА ФАЙЛА")
        self.preview_inventory_chip.setText("ИНВЕНТАРЬ ПРОВЕРЯЕТСЯ")

    def set_analysis_error(self, message: str, *, details: str | None = None) -> None:
        self._technical_details = technical_details(details or "")
        self.error_label.setText(message)
        self.error_label.setToolTip("")
        self.error_label.setVisible(True)
        self.details_button.setVisible(bool(self._technical_details))
        self.preview_name.setText("Сохранение не открыто")
        self.preview_meta.setText("Предыдущий файл остался открыт. Новое сохранение не загружено.")
        self.preview_meta.setToolTip("")
        self.preview_metadata.setVisible(False)
        self.preview_meta.setVisible(True)
        self.preview_status.setVisible(True)
        self.preview_status.setText("НЕ УДАЛОСЬ ОТКРЫТЬ")
        self.preview_status.setProperty("tone", "danger")
        self.preview_status.style().unpolish(self.preview_status)
        self.preview_status.style().polish(self.preview_status)
        self.open_button.setEnabled(False)
        self.preview_integrity_chip.setText("НЕ ПРОВЕРЕНО")
        self.preview_inventory_chip.setText("ИНВЕНТАРЬ НЕ ПРОЧИТАН")
        self.open_button.setText("ВЫБРАТЬ ДРУГОЙ ФАЙЛ")

    def _show_technical_details(self) -> None:
        if not self._technical_details:
            return
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(self._technical_details, self)
        self._details_dialog.open()

    def set_snapshot(self, snapshot: Any | None) -> None:
        """Refresh the selected-save detail from an already verified snapshot."""

        self._snapshot = snapshot
        self._update_preview()

    def set_recent_activity(
        self,
        entries: Iterable[tuple[str, str, str] | tuple[str, str, str, str]],
    ) -> None:
        """Render only operations supplied by the current session or journal."""

        normalized: list[tuple[str, str, str, str]] = []
        for entry in entries:
            if len(entry) == 4:
                label, target, occurred_at, status = entry
            else:
                label, target, status = entry
                occurred_at = ""
            normalized.append((label, target, occurred_at, status))
        self._activity_entries = normalized[-4:]
        if not self._activity_entries:
            self.activity_label.setText("Нет подтверждённых операций в текущем сеансе")
            self.activity_table.setRowCount(0)
            return
        visible = tuple(reversed(self._activity_entries))
        self.activity_label.setText(
            "\n".join(
                f"{label} · {target} · {occurred_at} · {status}"
                for label, target, occurred_at, status in visible
            )
        )
        self.activity_table.setRowCount(0)
        for row, (label, target, occurred_at, status) in enumerate(visible):
            self.activity_table.insertRow(row)
            for column, value in enumerate(
                (label, target, self._activity_time(occurred_at), status)
            ):
                item = QTableWidgetItem(value)
                if column == 0:
                    label_folded = label.casefold()
                    icon_name = (
                        "cloud.svg"
                        if "cloud" in label_folded
                        else "backups.svg"
                        if "коп" in label_folded or "резерв" in label_folded
                        else "history.svg"
                    )
                    icon = QIcon(str(_SHELL_ICONS / icon_name))
                    if not icon.isNull():
                        item.setIcon(icon)
                if column == 3 and status.startswith(("Проверено", "SHA ")):
                    item.setForeground(QColor("#7BCB62"))
                self.activity_table.setItem(row, column, item)
            self.activity_table.setRowHeight(row, 31)

    @staticmethod
    def _activity_time(value: str) -> str:
        if not value:
            return "—"
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            return _modified_text(int(timestamp * 1_000_000_000))
        except (OverflowError, OSError, ValueError):
            return value

    def append_recent_activity(
        self, label: str, target: str, status: str, occurred_at: str = ""
    ) -> None:
        self.set_recent_activity(
            (*self._activity_entries, (label, target, occurred_at, status))
        )

    def set_recent_activity_from_snapshot(self, snapshot: Any, *, operation: str) -> None:
        """Record a fact from a newly inspected snapshot without fabricating metadata."""

        self.append_recent_activity(
            operation,
            Path(getattr(snapshot, "path", "—")).name,
            "Файл проверен" if snapshot.info.crc_ok else "Файл повреждён или изменён",
            datetime.now().astimezone().isoformat(timespec="minutes"),
        )

    def _family_slots(self, family: str | None) -> list[SaveSlot]:
        slots = [slot for slot in self._slots if family is None or _slot_family(slot) == family]
        query = self.search_edit.text().strip().casefold()
        if query:
            slots = [slot for slot in slots if query in f"{slot.path.name} {slot.game_title} {slot.status_text}".casefold()]
        reverse = self.sort_combo.currentData() != "oldest"
        return sorted(slots, key=lambda slot: slot.modified_ns, reverse=reverse)

    @staticmethod
    def _row_subtitle(slot: SaveSlot) -> str:
        stem = slot.path.stem.casefold()
        if "auto" in stem:
            return "Автосохранение"
        if "quick" in stem:
            return "Быстрое сохранение"
        if "manual" in stem:
            return "Ручное сохранение"
        release_id = slot.detected_release_id or slot.candidate_release_id
        if release_id:
            try:
                release = release_by_id(release_id)
            except KeyError:
                release = None
            if release is not None:
                if release.edition == "enhanced":
                    return "Enhanced Edition"
                if release.family == "stalker2":
                    return "S.T.A.L.K.E.R. 2"
                return "Оригинальная версия"
        return "Формат не определён"

    def _set_save_title_cell(self, row: int, slot: SaveSlot) -> None:
        host = QWidget(self.save_table)
        host.setObjectName("librarySaveTitleCell")
        host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(14)

        thumbnail = QLabel(host)
        thumbnail.setObjectName("libraryRowThumbnail")
        thumbnail.setFixedSize(84, 50)
        art_path = self._thumbnail_art_path(slot)
        source = self._row_thumbnail_cache.get(art_path)
        if source is None:
            source = QPixmap(str(art_path))
            if not source.isNull():
                scaled = source.scaled(
                    QSize(84, 50),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = 0 if art_path.name == "preview_zone.png" else max(
                    0, (scaled.width() - 84) // 2
                )
                y = max(0, (scaled.height() - 50) // 2)
                source = scaled.copy(x, y, 84, 50)
                self._row_thumbnail_cache[art_path] = source
        if not source.isNull():
            thumbnail.setPixmap(source)
        thumbnail.setToolTip(
            "Декоративное изображение интерфейса; формат файла им не определяется."
        )
        layout.addWidget(thumbnail, 0)

        text_column = QWidget(host)
        text_column.setObjectName("libraryRowText")
        text_column.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        text_layout = QVBoxLayout(text_column)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        title = QLabel(slot.path.stem, text_column)
        title.setObjectName("libraryRowTitle")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        subtitle = QLabel(self._row_subtitle(slot), text_column)
        subtitle.setObjectName("libraryRowSubtitle")
        subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        text_layout.addWidget(title, 0, Qt.AlignmentFlag.AlignBottom)
        text_layout.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(text_column, 1)
        self.save_table.setCellWidget(row, 0, host)

    @staticmethod
    def _thumbnail_art_path(slot: SaveSlot) -> Path:
        asset = _ROW_THUMBNAIL_ASSETS.get(_slot_family(slot), "preview_zone.png")
        return _SHELL_ASSETS / asset

    def _render_game_list(self) -> None:
        previous = self.game_list.currentRow()
        self.game_list.blockSignals(True)
        self.game_list.clear()
        all_item = QListWidgetItem(f"ВСЕ ИГРЫ\n{len(self._slots)} сохранений")
        all_icon = QIcon(str(_SHELL_ICONS / "game-grid.svg"))
        if not all_icon.isNull():
            all_item.setIcon(all_icon)
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        all_item.setSizeHint(QSize(0, 61))
        self.game_list.addItem(all_item)
        for family in GAME_IDS:
            count = len([slot for slot in self._slots if _slot_family(slot) == family])
            label = self._family_labels.get(family, GAME_TITLES.get(family, family))
            item = QListWidgetItem(f"{label}\n{count} сохранений")
            family_icon = QIcon(str(_SHELL_ICONS / "radiation.svg"))
            if not family_icon.isNull():
                item.setIcon(family_icon)
            item.setData(Qt.ItemDataRole.UserRole, family)
            item.setSizeHint(QSize(0, 60))
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
            family_title = self._family_labels.get(_slot_family(slot), slot.game_title)
            table_game = family_title if slot.format_id else slot.candidate_game_title
            if slot.format_id is None and slot.candidate_release_id:
                try:
                    candidate_release = release_by_id(slot.candidate_release_id)
                except KeyError:
                    candidate_release = None
                if candidate_release is not None and candidate_release.edition == "enhanced":
                    edition_title = candidate_release.title.rsplit(" — ", 1)[-1]
                    table_game = f"{family_title}\n{edition_title}"
            values = (
                slot.path.name,
                table_game,
                _modified_text(slot.modified_ns),
                human_size(slot.size),
                "",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem("" if column == 0 else value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, str(slot.path))
                self.save_table.setItem(table_row, column, cell)
            self._set_save_title_cell(table_row, slot)
            status_cell = QWidget(self.save_table)
            status_cell.setObjectName("librarySaveStatusCell")
            status_cell.setToolTip("")
            status_icon = QLabel("●", status_cell)
            status_icon.setObjectName(
                "libraryReadyDot" if slot.format_id is not None else "libraryCandidateDot"
            )
            ready_label = QLabel(
                "Готово" if slot.format_id is not None else "Только просмотр",
                status_cell,
            )
            ready_label.setObjectName("libraryReadyLabel")
            release = None
            if slot.candidate_release_id:
                try:
                    release = release_by_id(slot.candidate_release_id)
                except KeyError:
                    release = None
            candidate_chip = status_chip(
                "Редактируемый" if slot.format_id is not None else (
                    "Экспериментальный" if release is not None and release.edition == "enhanced"
                    else "Не распознано"
                ),
                status_cell,
                tone="success" if slot.format_id is not None else "warning",
            )
            candidate_chip.setObjectName("libraryEditableChip")
            if slot.format_id is not None:
                status_row_layout = QHBoxLayout(status_cell)
                status_row_layout.setContentsMargins(4, 0, 2, 0)
                status_row_layout.setSpacing(4)
                status_row_layout.addWidget(status_icon)
                status_row_layout.addWidget(ready_label)
                status_row_layout.addStretch(1)
                status_row_layout.addWidget(candidate_chip)
            else:
                status_column_layout = QVBoxLayout(status_cell)
                status_column_layout.setContentsMargins(4, 2, 2, 2)
                status_column_layout.setSpacing(1)
                state_row = QHBoxLayout()
                state_row.setContentsMargins(0, 0, 0, 0)
                state_row.setSpacing(4)
                state_row.addWidget(status_icon)
                state_row.addWidget(ready_label)
                state_row.addStretch(1)
                status_column_layout.addLayout(state_row)
                status_column_layout.addWidget(candidate_chip, 0, Qt.AlignmentFlag.AlignLeft)
            self.save_table.setCellWidget(table_row, 4, status_cell)
            self.save_table.setRowHeight(table_row, 67)
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
        selected_row = self.save_table.currentRow() if slot is not None else -1
        for row in range(self.save_table.rowCount()):
            title_cell = self.save_table.cellWidget(row, 0)
            if title_cell is None:
                continue
            is_selected = row == selected_row
            title_cell.setProperty("selected", is_selected)
            title_cell.style().unpolish(title_cell)
            title_cell.style().polish(title_cell)
            for name in ("libraryRowTitle", "libraryRowSubtitle"):
                label = title_cell.findChild(QLabel, name)
                if label is None:
                    continue
                label.setProperty("rowSelected", is_selected)
                label.style().unpolish(label)
                label.style().polish(label)
        self.open_button.setEnabled(slot is not None)
        self.restore_button.setEnabled(slot is not None)
        if slot is None:
            self.preview_name.setText("Сохранение не выбрано")
            self.preview_meta.setText("Выбери сохранение, чтобы увидеть подробности.")
            self.preview_metadata.setVisible(False)
            self.preview_meta.setVisible(True)
            self.preview_status.setVisible(False)
            self.money_summary.setText("—")
            self.items_summary.setText("—")
            self.equipment_summary.setText("—")
            self.condition_summary.setText("—")
            self.preview_editable_chip.setText("ПРОВЕРИТСЯ ПРИ ОТКРЫТИИ")
            self.preview_integrity_chip.setText("НЕ ПРОВЕРЕНО")
            self.preview_inventory_chip.setText("ИНВЕНТАРЬ —")
            return
        self.preview_name.setText(slot.path.name)
        snapshot = self._snapshot
        snapshot_matches = bool(
            snapshot is not None
            and Path(snapshot.path).resolve() == Path(slot.path).resolve()
        )
        if snapshot_matches and snapshot is not None:
            info = snapshot.info
            capabilities = getattr(snapshot, "capabilities", None)
            editable = bool(
                capabilities is not None
                and any(
                    capabilities.support(name).writable
                    for name in ("edit_money", "edit_stacks", "edit_durability")
                )
            )
            self.preview_editable_chip.setText("РЕДАКТИРУЕМЫЙ" if editable else "ТОЛЬКО ПРОСМОТР")
            self.preview_editable_chip.setProperty("tone", "success" if editable else "neutral")
            money = human_money(info.money) if info.money is not None else "—"
            self.money_summary.setText(f"{money} ₽")
            self.items_summary.setText(str(len(info.inventory)))
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
            self.equipment_summary.setText(f"{equipment_count} комплектов")
            self.condition_summary.setText(average_condition)
            self.preview_integrity_chip.setText(
            "Сохранение проверено" if info.crc_ok else "Файл не прошёл проверку"
            )
            self.preview_inventory_chip.setText(f"ИНВЕНТАРЬ · {len(info.inventory)}")
        else:
            self.preview_editable_chip.setText("ПРОВЕРИТСЯ ПРИ ОТКРЫТИИ")
            self.preview_editable_chip.setProperty("tone", "neutral")
            self.preview_integrity_chip.setText("НЕ ПРОВЕРЕНО")
            self.preview_inventory_chip.setText("ИНВЕНТАРЬ —")
            self.money_summary.setText("—")
            self.items_summary.setText("—")
            self.equipment_summary.setText("—")
            self.condition_summary.setText("—")
        for chip in (self.preview_editable_chip, self.preview_integrity_chip):
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        source = (
            "Steam Cloud"
            if snapshot_matches and getattr(self._snapshot, "source_kind", None) == "cloud"
            else "Локальное сохранение"
        )
        game_title = slot.game_title or slot.candidate_game_title
        self.preview_game_value.setText(game_title)
        self.preview_game_value.setToolTip(game_title)
        self.preview_source_value.setText(source)
        self.preview_date_value.setText(_modified_text(slot.modified_ns))
        self.preview_size_value.setText(human_size(slot.size))
        if snapshot is not None and snapshot_matches:
            self.preview_integrity_value.setText(
                "Сохранение проверено" if snapshot.info.crc_ok else "Файл не прошёл проверку"
            )
            self.preview_integrity_value.setProperty(
                "integrityState", "verified" if snapshot.info.crc_ok else "warning"
            )
        else:
            self.preview_integrity_value.setText("Не проверено")
            self.preview_integrity_value.setProperty("integrityState", "unknown")
        self.preview_integrity_value.style().unpolish(self.preview_integrity_value)
        self.preview_integrity_value.style().polish(self.preview_integrity_value)
        self.preview_metadata.setVisible(True)
        self.preview_meta.setVisible(False)
        self.preview_status.setVisible(False)
        self.open_button.setText("ОТКРЫТЬ СОХРАНЕНИЕ  →")

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
