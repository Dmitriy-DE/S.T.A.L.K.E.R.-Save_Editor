"""Zone-style launcher for the local save library.

The launcher is deliberately a view over :mod:`ui.save_slots_view`.  It does
not infer an installed game from a folder name and it never writes to a game
directory.  A save found on disk is shown as a candidate until the shared
format detector accepts its bytes.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.releases import release_by_id

from .formatting import human_size
from .save_slots_view import GAME_IDS, GAME_TITLES, SaveDiscovery, SaveSlot

_GAME_MENU_TITLES: dict[str, str] = {
    "stalker2": "S.T.A.L.K.E.R. 2",
    "cop": "Call of Pripyat",
    "clear_sky": "Clear Sky",
    "soc": "Shadow of Chernobyl",
}


def _modified_text(modified_ns: int) -> str:
    from datetime import datetime

    try:
        return datetime.fromtimestamp(modified_ns / 1_000_000_000).strftime(
            "%Y-%m-%d %H:%M"
        )
    except (OverflowError, OSError, ValueError):
        return "неизвестно"


def _slot_family(slot: SaveSlot) -> str:
    """Resolve a slot to a stable family without treating paths as proof."""

    if slot.candidate_game_id in GAME_IDS:
        return slot.candidate_game_id
    for release_id in (slot.detected_release_id, slot.format_id, slot.candidate_release_id):
        if not release_id:
            continue
        try:
            return release_by_id(release_id).family
        except KeyError:
            continue
    return slot.candidate_game_id


class LauncherView(QWidget):
    """Main library screen shown before a save is opened."""

    open_requested = Signal(object)
    import_requested = Signal()
    cloud_requested = Signal()
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._slots: tuple[SaveSlot, ...] = ()
        self._searched_paths: tuple[Path, ...] = ()
        self._installed_families: set[str] = set()
        self._build_ui()
        self._render_game_list()

    def _build_ui(self) -> None:
        self.setObjectName("launcher")
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 28, 34, 28)
        root.setSpacing(16)

        header = QFrame()
        header.setObjectName("launcherHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(14)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        brand = QLabel("S.T.A.L.K.E.R.")
        brand.setObjectName("launcherBrand")
        title_box.addWidget(brand)
        title = QLabel("БИБЛИОТЕКА СОХРАНЕНИЙ")
        title.setObjectName("launcherTitle")
        title_box.addWidget(title)
        subtitle = QLabel(
            "Выбери игру и сохранение. Файл можно открыть отдельно — установленная игра не требуется."
        )
        subtitle.setObjectName("launcherSubtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box, 1)

        self.refresh_button = QPushButton("ОБНОВИТЬ ЗОНУ")
        self.refresh_button.setObjectName("launcherSecondaryButton")
        self.refresh_button.clicked.connect(self.refresh_requested)
        header_layout.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignTop)
        self.cloud_button = QPushButton("STEAM CLOUD")
        self.cloud_button.setObjectName("launcherCloudButton")
        self.cloud_button.setToolTip(
            "Открыть удалённые сейвы S.T.A.L.K.E.R. 2 через Steam helper"
        )
        self.cloud_button.clicked.connect(self.cloud_requested)
        header_layout.addWidget(self.cloud_button, 0, Qt.AlignmentFlag.AlignTop)
        self.import_button = QPushButton("ИМПОРТ СЕЙВА…")
        self.import_button.setObjectName("launcherPrimaryButton")
        self.import_button.setToolTip(
            "Открыть скачанный файл и проверить его содержимое без установленной игры"
        )
        self.import_button.clicked.connect(self.import_requested)
        header_layout.addWidget(self.import_button, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(14)

        games_panel = QFrame()
        games_panel.setObjectName("launcherGamesPanel")
        games_panel.setMinimumWidth(360)
        games_layout = QVBoxLayout(games_panel)
        games_layout.setContentsMargins(16, 16, 16, 16)
        games_layout.setSpacing(8)
        games_heading = QLabel("ИГРЫ ЗОНЫ")
        games_heading.setObjectName("launcherPanelHeading")
        games_layout.addWidget(games_heading)
        games_hint = QLabel("Найденные установки и локальные сейвы")
        games_hint.setObjectName("launcherPanelHint")
        games_hint.setWordWrap(True)
        games_layout.addWidget(games_hint)
        self.game_list = QListWidget()
        self.game_list.setObjectName("launcherGameList")
        self.game_list.setWordWrap(True)
        self.game_list.setUniformItemSizes(False)
        self.game_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.game_list.currentRowChanged.connect(self._render_saves)
        games_layout.addWidget(self.game_list, 1)
        body.addWidget(games_panel, 0)

        saves_panel = QFrame()
        saves_panel.setObjectName("launcherSavesPanel")
        saves_layout = QVBoxLayout(saves_panel)
        saves_layout.setContentsMargins(16, 16, 16, 16)
        saves_layout.setSpacing(8)
        saves_heading = QHBoxLayout()
        saves_title_box = QVBoxLayout()
        saves_title_box.setSpacing(3)
        self.selection_title = QLabel("ВСЕ СОХРАНЕНИЯ")
        self.selection_title.setObjectName("launcherPanelHeading")
        saves_title_box.addWidget(self.selection_title)
        self.search_label = QLabel("Проверяю стандартные каталоги сохранений…")
        self.search_label.setObjectName("launcherPanelHint")
        saves_title_box.addWidget(self.search_label)
        saves_heading.addLayout(saves_title_box, 1)
        self.open_button = QPushButton("ОТКРЫТЬ В РЕДАКТОРЕ")
        self.open_button.setObjectName("launcherOpenButton")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_selected)
        saves_heading.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignTop)
        saves_layout.addLayout(saves_heading)

        self.save_table = QTableWidget(0, 5)
        self.save_table.setObjectName("launcherSaveTable")
        self.save_table.setHorizontalHeaderLabels(
            ("СОХРАНЕНИЕ", "ИГРА", "ИЗМЕНЁН", "РАЗМЕР", "СОСТОЯНИЕ")
        )
        self.save_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.save_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.save_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.save_table.setAlternatingRowColors(True)
        self.save_table.verticalHeader().setVisible(False)
        header = self.save_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.save_table.itemSelectionChanged.connect(self._update_open_state)
        self.save_table.cellDoubleClicked.connect(lambda row, _column: self._open_row(row))
        saves_layout.addWidget(self.save_table, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel(
            "Библиотека готова. Можно импортировать скачанный сейв напрямую."
        )
        self.status_label.setObjectName("launcherStatus")
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)
        self.path_count_label = QLabel("ПУТИ: —")
        self.path_count_label.setObjectName("launcherPathCount")
        footer.addWidget(self.path_count_label, 0, Qt.AlignmentFlag.AlignBottom)
        saves_layout.addLayout(footer)
        body.addWidget(saves_panel, 1)
        root.addLayout(body, 1)

    def set_installed_families(self, families: Iterable[str]) -> None:
        self._installed_families = set(families)
        self._render_game_list()

    def set_discovery(self, discovery: SaveDiscovery) -> None:
        self._slots = tuple(discovery.slots)
        self._searched_paths = tuple(discovery.searched_paths)
        self.search_label.setText(
            f"Проверено каталогов: {len(self._searched_paths)} · найдено файлов: {len(self._slots)}"
        )
        self.path_count_label.setText(f"ПУТИ: {len(self._searched_paths)}")
        if self._slots:
            self.status_label.setText(
                f"Найдено сохранений: {len(self._slots)}. Открытие выполняется через общий анализатор формата."
            )
        else:
            self.status_label.setText(
                "Локальные сохранения не найдены. Импортируй скачанный файл — игра на компьютере не нужна."
            )
        self._render_game_list()

    def set_error(self, message: str) -> None:
        self.status_label.setText(f"Поиск сохранений не выполнен: {message}")

    def _family_slots(self, family: str | None) -> list[SaveSlot]:
        if family is None:
            return list(self._slots)
        return [slot for slot in self._slots if _slot_family(slot) == family]

    def _status_for_family(self, family: str) -> str:
        count = len(self._family_slots(family))
        if family in self._installed_families:
            return f"УСТАНОВЛЕНА · {count} СЕЙВОВ"
        if count:
            return f"СЕЙВОВ: {count} · ИГРА НЕ УСТАНОВЛЕНА"
        return "ИГРА НЕ НАЙДЕНА · ИМПОРТ"

    def _render_game_list(self) -> None:
        previous = self.game_list.currentRow()
        self.game_list.blockSignals(True)
        self.game_list.clear()
        self.game_list.addItem("ВСЕ ИГРЫ")
        self.game_list.item(0).setData(Qt.ItemDataRole.UserRole, None)
        self.game_list.item(0).setToolTip("Показать сохранения всех поддержанных игр")
        for family in GAME_IDS:
            item = QListWidgetItem(
                f"{_GAME_MENU_TITLES[family]}  ·  {self._status_for_family(family)}"
            )
            item.setSizeHint(QSize(0, 54))
            item.setData(Qt.ItemDataRole.UserRole, family)
            item.setToolTip(GAME_TITLES[family])
            self.game_list.addItem(item)
        row = previous if 0 <= previous < self.game_list.count() else 0
        self.game_list.setCurrentRow(row)
        self.game_list.blockSignals(False)
        self._render_saves(row)

    def _render_saves(self, row: int) -> None:
        if row < 0 or row >= self.game_list.count():
            return
        item = self.game_list.item(row)
        family = item.data(Qt.ItemDataRole.UserRole)
        family = str(family) if family is not None else None
        slots = self._family_slots(family)
        self.selection_title.setText(
            "ВСЕ СОХРАНЕНИЯ" if family is None else GAME_TITLES.get(family, family)
        )
        self.save_table.setRowCount(0)
        for slot in slots:
            table_row = self.save_table.rowCount()
            self.save_table.insertRow(table_row)
            values = (
                slot.path.name,
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
        self._update_open_state()

    def _update_open_state(self) -> None:
        selected = self.save_table.selectedItems()
        self.open_button.setEnabled(bool(selected))

    def _open_row(self, row: int) -> None:
        if row < 0 or row >= self.save_table.rowCount():
            return
        item = self.save_table.item(row, 0)
        if item is None:
            return
        self.open_requested.emit(Path(str(item.data(Qt.ItemDataRole.UserRole))))

    def open_selected(self) -> None:
        selected = self.save_table.selectedItems()
        if not selected:
            return
        self._open_row(selected[0].row())
