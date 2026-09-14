"""Read-only local save discovery and slot selection for the Qt shell."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeAlias

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.formats import SaveFormat, detect
from editor.platforms import save_search_paths

GAME_TITLES: dict[str, str] = {
    "stalker2": "S.T.A.L.K.E.R. 2: Heart of Chornobyl",
    "cop": "S.T.A.L.K.E.R.: Call of Pripyat",
    "clear_sky": "S.T.A.L.K.E.R.: Clear Sky",
    "soc": "S.T.A.L.K.E.R.: Shadow of Chernobyl",
}
GAME_IDS: tuple[str, ...] = ("stalker2", "cop", "clear_sky", "soc")


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _modified_text(modified_ns: int) -> str:
    try:
        return datetime.fromtimestamp(modified_ns / 1_000_000_000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (OverflowError, OSError, ValueError):
        return "неизвестно"


@dataclass(frozen=True)
class SaveSlot:
    """One regular ``.sav`` file found in a read-only candidate directory.

    ``candidate_game_*`` describes why a directory was searched.  The actual
    ``game_id`` and ``game_title`` properties are populated only when a
    registered format accepts the file bytes; a directory name never counts as
    format detection.
    """

    path: Path
    candidate_game_id: str
    candidate_game_title: str
    size: int
    modified_ns: int
    format_id: str | None = None
    format_title: str | None = None
    detection_error: str | None = None

    @property
    def game_id(self) -> str | None:
        """Return the content-detected game id, or ``None`` if unknown."""

        return self.format_id

    @property
    def game_title(self) -> str:
        """Return the content-detected title, or an honest unknown marker."""

        return self.format_title or "Игра не определена"

    @property
    def status_text(self) -> str:
        """Return the user-facing format status for the slot table."""

        if self.format_id is not None:
            title = self.format_title or self.format_id
            return f"{title} [{self.format_id}]"
        if self.detection_error:
            return f"Ошибка чтения: {self.detection_error}"
        return "Не распознано ни одним форматом"


@dataclass(frozen=True)
class SaveDiscovery:
    """Immutable result of one local save search."""

    slots: tuple[SaveSlot, ...]
    searched_paths: tuple[Path, ...]


SearchPathsFn: TypeAlias = Callable[[str], Sequence[Path]]
DetectFn: TypeAlias = Callable[[bytes], SaveFormat | None]
SlotDiscoveryFn: TypeAlias = Callable[[], SaveDiscovery]


def discover_save_slots(
    *,
    game_ids: Sequence[str] = GAME_IDS,
    search_paths_fn: SearchPathsFn = save_search_paths,
    detect_fn: DetectFn = detect,
) -> SaveDiscovery:
    """Enumerate candidate ``.sav`` files without opening or writing them.

    The file bytes are read only to run the shared content detector.  A
    directory that does not exist is still included in ``searched_paths`` so
    an empty result can explain exactly what was checked.
    """

    searched_paths: list[Path] = []
    searched_seen: set[Path] = set()
    slots: list[SaveSlot] = []
    slot_seen: set[Path] = set()

    for game_id in game_ids:
        candidate_title = GAME_TITLES.get(game_id, game_id)
        for raw_directory in search_paths_fn(game_id):
            directory = Path(raw_directory).expanduser()
            if directory not in searched_seen:
                searched_seen.add(directory)
                searched_paths.append(directory)
            try:
                if not directory.is_dir():
                    continue
                entries = tuple(directory.iterdir())
            except OSError:
                continue

            for path in entries:
                if path in slot_seen or path.suffix.casefold() != ".sav":
                    continue
                try:
                    if not path.is_file():
                        continue
                    stat = path.stat()
                except OSError:
                    continue
                slot_seen.add(path)
                try:
                    data = path.read_bytes()
                except OSError as exc:
                    slots.append(
                        SaveSlot(
                            path=path,
                            candidate_game_id=game_id,
                            candidate_game_title=candidate_title,
                            size=stat.st_size,
                            modified_ns=stat.st_mtime_ns,
                            detection_error=f"{type(exc).__name__}: {exc}",
                        )
                    )
                    continue

                try:
                    format_ = detect_fn(data)
                except Exception as exc:
                    slots.append(
                        SaveSlot(
                            path=path,
                            candidate_game_id=game_id,
                            candidate_game_title=candidate_title,
                            size=stat.st_size,
                            modified_ns=stat.st_mtime_ns,
                            detection_error=f"{type(exc).__name__}: {exc}",
                        )
                    )
                    continue

                slots.append(
                    SaveSlot(
                        path=path,
                        candidate_game_id=game_id,
                        candidate_game_title=candidate_title,
                        size=stat.st_size,
                        modified_ns=stat.st_mtime_ns,
                        format_id=format_.id if format_ is not None else None,
                        format_title=format_.title if format_ is not None else None,
                    )
                )

    slots.sort(key=lambda slot: (-slot.modified_ns, str(slot.path).casefold()))
    return SaveDiscovery(tuple(slots), tuple(searched_paths))


class SlotDiscoveryWorker(QThread):
    """Run local path enumeration and content detection outside the UI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        discovery_fn: SlotDiscoveryFn,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.discovery_fn = discovery_fn

    def run(self) -> None:
        try:
            self.completed.emit(self.discovery_fn())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class SaveSlotsView(QWidget):
    """Display discovered local slots and emit a path only on user action."""

    discovery_ready = Signal(object)
    discovery_failed = Signal(str)
    open_requested = Signal(object)

    def __init__(
        self,
        discovery_fn: SlotDiscoveryFn = discover_save_slots,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.discovery_fn = discovery_fn
        self._slots: tuple[SaveSlot, ...] = ()
        self._searched_paths: tuple[Path, ...] = ()
        self._worker: SlotDiscoveryWorker | None = None
        self._build_ui()

    @property
    def slots(self) -> tuple[SaveSlot, ...]:
        return self._slots

    @property
    def searched_paths(self) -> tuple[Path, ...]:
        return self._searched_paths

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.refresh_button = QPushButton("Обновить список")
        self.refresh_button.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_button)
        self.status_label = QLabel("Список ещё не обновлялся")
        self.status_label.setWordWrap(True)
        toolbar.addWidget(self.status_label, 1)
        layout.addLayout(toolbar)

        self.search_paths_label = QLabel("Искали в: список появится после обновления")
        self.search_paths_label.setWordWrap(True)
        self.search_paths_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.search_paths_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Слот", "Размер", "Изменён", "Игра / статус"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._open_row)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel(
            "Сохранения ещё не искали. Нажми «Обновить список»; слот открывается "
            "только двойным щелчком."
        )
        self.empty_label.setWordWrap(True)
        self.empty_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.empty_label)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

    def refresh(self) -> None:
        """Start one read-only discovery run; never open a slot implicitly."""

        if self._worker is not None and self._worker.isRunning():
            return
        self.refresh_button.setEnabled(False)
        self.status_label.setText("Поиск сохранений… файлы не изменяются")
        self.error_label.clear()
        self.error_label.setVisible(False)
        worker = SlotDiscoveryWorker(self.discovery_fn, self)
        worker.completed.connect(self._on_discovery_ready)
        worker.failed.connect(self._on_discovery_failed)
        worker.finished.connect(self._on_worker_finished)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _on_discovery_ready(self, discovery: SaveDiscovery) -> None:
        self._set_discovery(discovery)
        self.discovery_ready.emit(discovery)

    def _on_discovery_failed(self, message: str) -> None:
        self.status_label.setText("Поиск не выполнен; текущий список сохранён")
        self.error_label.setText(f"Не удалось найти сохранения: {message}")
        self.error_label.setVisible(True)
        self.discovery_failed.emit(message)

    def _on_worker_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self._worker = None

    def _set_discovery(self, discovery: SaveDiscovery) -> None:
        self._slots = tuple(discovery.slots)
        self._searched_paths = tuple(Path(path) for path in discovery.searched_paths)
        self.table.setRowCount(len(self._slots))
        for row, slot in enumerate(self._slots):
            values = (
                slot.path.name,
                _human_size(slot.size),
                _modified_text(slot.modified_ns),
                slot.status_text,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(row, column, item)
        self.table.clearSelection()

        paths = "\n".join(f"• {path}" for path in self._searched_paths)
        self.search_paths_label.setText(
            "Искали в (каталоги не создавались и не изменялись):\n"
            + (paths or "• пути не определены")
        )
        if self._slots:
            self.empty_label.setText(
                f"Найдено сохранений: {len(self._slots)}. "
                "Открытие выполняется только двойным щелчком по строке."
            )
            self.status_label.setText(f"Найдено сохранений: {len(self._slots)}")
        else:
            self.empty_label.setText(
                "Сохранения не найдены — это не ошибка. Проверь пути выше или "
                "выбери файл вручную кнопкой «Открыть .sav…»."
            )
            self.status_label.setText("Сохранения не найдены; ручной выбор доступен")
        self.error_label.clear()
        self.error_label.setVisible(False)

    def _open_row(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._slots):
            self.open_requested.emit(self._slots[row].path)


__all__ = [
    "GAME_IDS",
    "GAME_TITLES",
    "SaveDiscovery",
    "SaveSlot",
    "SaveSlotsView",
    "SlotDiscoveryFn",
    "SlotDiscoveryWorker",
    "discover_save_slots",
]
