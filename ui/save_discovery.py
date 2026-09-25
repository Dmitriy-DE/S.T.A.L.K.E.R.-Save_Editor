"""Read-only local save discovery and slot selection for the Qt shell."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeAlias

from PySide6.QtCore import QObject, QThread, Signal

from editor.formats import SaveFormat, detect, detect_fast
from editor.i18n import tr
from editor.platforms import save_search_paths
from editor.releases import official_releases, release_by_id

GAME_TITLES: dict[str, str] = {
    "stalker2": "S.T.A.L.K.E.R. 2: Heart of Chornobyl",
    "cop": "S.T.A.L.K.E.R.: Call of Pripyat",
    "clear_sky": "S.T.A.L.K.E.R.: Clear Sky",
    "soc": "S.T.A.L.K.E.R.: Shadow of Chernobyl",
}
GAME_IDS: tuple[str, ...] = ("stalker2", "cop", "clear_sky", "soc")
RELEASE_IDS: tuple[str, ...] = tuple(release.id for release in official_releases())
RELEASE_TITLES: dict[str, str] = {
    release.id: release.title for release in official_releases()
}
SAVE_SUFFIXES = frozenset({".sav", ".scop", ".scs"})


def _modified_text(modified_ns: int) -> str:
    try:
        return datetime.fromtimestamp(modified_ns / 1_000_000_000).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (OverflowError, OSError, ValueError):
        return tr("неизвестно")


@dataclass(frozen=True)
class SaveSlot:
    """One candidate save file found in a read-only directory.

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
    candidate_release_id: str | None = None
    detected_release_id: str | None = None
    unsupported_reason: UnsupportedSaveReason | None = None

    @property
    def game_id(self) -> str | None:
        """Return the content-detected game id, or ``None`` if unknown."""

        return self.format_id

    @property
    def game_title(self) -> str:
        """Return the content-detected title, or an honest unknown marker."""

        return self.format_title or tr("Игра не определена")

    @property
    def status_text(self) -> str:
        """Return the user-facing format status for the slot table."""

        if self.format_id is not None:
            title = self.format_title or self.format_id
            return f"{title} [{self.format_id}]"
        if self.detection_error:
            return tr("Ошибка чтения: {0}", self.detection_error)
        if self.unsupported_reason is not None:
            return self.unsupported_reason.message
        return tr("Не распознано ни одним форматом")


@dataclass(frozen=True)
class UnsupportedSaveReason:
    """Structured reason kept with a candidate that cannot be opened."""

    code: str
    message: str


@dataclass(frozen=True)
class SaveDiscovery:
    """Immutable result of one local save search."""

    slots: tuple[SaveSlot, ...]
    searched_paths: tuple[Path, ...]


def _slot_family(slot: SaveSlot) -> str:
    """Resolve a slot to a stable family without treating paths as proof."""

    if slot.candidate_game_id in GAME_IDS:
        return slot.candidate_game_id
    for release_id in (slot.detected_release_id, slot.format_id, slot.candidate_release_id):
        if not release_id:
            continue
        try:
            descriptor = release_by_id(release_id)
        except KeyError:
            continue
        return descriptor.family
    return slot.candidate_game_id


SearchPathsFn: TypeAlias = Callable[[str], Sequence[Path]]
DetectFn: TypeAlias = Callable[[bytes], SaveFormat | None]
SlotDiscoveryFn: TypeAlias = Callable[[], SaveDiscovery]
_DetectionCacheValue: TypeAlias = tuple[
    int, int, str | None, str | None, str | None, str | None, str | None
]

# Discovery is repeated when the user changes destinations/settings and when several
# windows are created by the UI test harness.  Cache only the content-detection
# result, never file bytes, and invalidate it on the ordinary size/mtime pair.
# Opening a row still performs a fresh full inspection and SHA check.
_DETECTION_CACHE: dict[tuple[Path, int], _DetectionCacheValue] = {}


def _unknown_format_reason(candidate_release_id: str) -> UnsupportedSaveReason:
    """Explain why a known official candidate cannot currently be opened."""

    try:
        descriptor = release_by_id(candidate_release_id)
    except KeyError:
        descriptor = None
    if descriptor is not None and descriptor.edition == "enhanced":
        return UnsupportedSaveReason(
            code="unsupported_release",
            message=(
                tr("Найден официальный сейв Enhanced Edition, но его формат ещё не подтверждён и не поддерживается")
            ),
        )
    if descriptor is not None and descriptor.family == "stalker2":
        # Saves written by the launch builds (v1.0.x, late 2024) use an older
        # player-data layout; the game upgrades a slot when it re-saves it.
        return UnsupportedSaveReason(
            code="unknown_format",
            message=(
                tr("Формат не распознан. Если это сохранение старой версии игры (конец 2024 года), загрузи его в S.T.A.L.K.E.R. 2 и сохрани заново — после этого редактор его откроет.")
            ),
        )
    return UnsupportedSaveReason(
        code="unknown_format",
        message=tr("Не распознано зарегистрированным форматом"),
    )


# S.T.A.L.K.E.R. 2 keeps its campaign index and telemetry next to the slots
# with the same ``.sav`` suffix.  They are not player saves and can never be
# opened by the editor, so the library must not list them.
_NON_SLOT_FILENAMES = frozenset({"campaignssave.sav", "analyticsdata.sav"})


def discover_save_slots(
    *,
    game_ids: Sequence[str] = GAME_IDS,
    release_ids: Sequence[str] | None = None,
    search_paths_fn: SearchPathsFn = save_search_paths,
    detect_fn: DetectFn = detect,
) -> SaveDiscovery:
    """Enumerate candidate save files without writing them.

    The file bytes are read only to run the shared content detector.  A
    directory that does not exist is still included in ``searched_paths`` so
    an empty result can explain exactly what was checked.
    """

    searched_paths: list[Path] = []
    searched_seen: set[Path] = set()
    slots: list[SaveSlot] = []
    slot_seen: set[Path] = set()
    detector: DetectFn = detect_fast if detect_fn is detect else detect_fn
    detector_key = 0 if detector is detect_fast else id(detector)

    selectors = tuple(game_ids if release_ids is None else release_ids)
    for selector in selectors:
        try:
            descriptor = release_by_id(selector)
        except KeyError:
            descriptor = None
        candidate_game_id = descriptor.family if descriptor is not None else selector
        candidate_release_id = descriptor.id if descriptor is not None else selector
        candidate_title = (
            descriptor.title
            if descriptor is not None
            else GAME_TITLES.get(selector, selector)
        )
        for raw_directory in search_paths_fn(selector):
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
                if path in slot_seen or path.suffix.casefold() not in SAVE_SUFFIXES:
                    continue
                if path.name.casefold() in _NON_SLOT_FILENAMES:
                    continue
                try:
                    if not path.is_file():
                        continue
                    stat = path.stat()
                except OSError:
                    continue
                slot_seen.add(path)
                cache_key = (path, detector_key)
                cached = _DETECTION_CACHE.get(cache_key)
                if cached is not None and cached[:2] == (stat.st_size, stat.st_mtime_ns):
                    slots.append(
                        SaveSlot(
                            path=path,
                            candidate_game_id=candidate_game_id,
                            candidate_game_title=candidate_title,
                            size=stat.st_size,
                            modified_ns=stat.st_mtime_ns,
                            format_id=cached[2],
                            format_title=cached[3],
                            detection_error=cached[5],
                            candidate_release_id=candidate_release_id,
                            detected_release_id=cached[4],
                            unsupported_reason=(
                                None
                                if cached[2] is not None
                                else (
                                    UnsupportedSaveReason(
                                        code=cached[6] or "detection_error",
                                        message=tr("Ошибка проверки: {0}", cached[5]),
                                    )
                                    if cached[5]
                                    else _unknown_format_reason(candidate_release_id)
                                )
                            ),
                        )
                    )
                    continue
                try:
                    data = path.read_bytes()
                except OSError as exc:
                    _DETECTION_CACHE[cache_key] = (
                        stat.st_size,
                        stat.st_mtime_ns,
                        None,
                        None,
                        None,
                        f"{type(exc).__name__}: {exc}",
                        "read_error",
                    )
                    slots.append(
                        SaveSlot(
                            path=path,
                            candidate_game_id=candidate_game_id,
                            candidate_game_title=candidate_title,
                            size=stat.st_size,
                            modified_ns=stat.st_mtime_ns,
                            detection_error=f"{type(exc).__name__}: {exc}",
                            candidate_release_id=candidate_release_id,
                            unsupported_reason=UnsupportedSaveReason(
                                code="read_error",
                                message=tr("Ошибка чтения: {0}: {1}", type(exc).__name__, exc),
                            ),
                        )
                    )
                    continue

                try:
                    format_ = detector(data)
                except Exception as exc:
                    _DETECTION_CACHE[cache_key] = (
                        stat.st_size,
                        stat.st_mtime_ns,
                        None,
                        None,
                        None,
                        f"{type(exc).__name__}: {exc}",
                        "detection_error",
                    )
                    slots.append(
                        SaveSlot(
                            path=path,
                            candidate_game_id=candidate_game_id,
                            candidate_game_title=candidate_title,
                            size=stat.st_size,
                            modified_ns=stat.st_mtime_ns,
                            detection_error=f"{type(exc).__name__}: {exc}",
                            candidate_release_id=candidate_release_id,
                            unsupported_reason=UnsupportedSaveReason(
                                code="detection_error",
                                message=tr("Ошибка проверки: {0}: {1}", type(exc).__name__, exc),
                            ),
                        )
                    )
                    continue

                _DETECTION_CACHE[cache_key] = (
                    stat.st_size,
                    stat.st_mtime_ns,
                    format_.id if format_ is not None else None,
                    format_.title if format_ is not None else None,
                    format_.release_id if format_ is not None else None,
                    None,
                    None,
                )
                slots.append(
                    SaveSlot(
                        path=path,
                        candidate_game_id=candidate_game_id,
                        candidate_game_title=candidate_title,
                        size=stat.st_size,
                        modified_ns=stat.st_mtime_ns,
                        format_id=format_.id if format_ is not None else None,
                        format_title=format_.title if format_ is not None else None,
                        candidate_release_id=candidate_release_id,
                        detected_release_id=(
                            format_.release_id if format_ is not None else None
                        ),
                        unsupported_reason=(
                            None
                            if format_ is not None
                            else _unknown_format_reason(candidate_release_id)
                        ),
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
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.discovery_fn = discovery_fn

    def run(self) -> None:
        try:
            self.completed.emit(self.discovery_fn())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class SlotDiscoveryController(QObject):
    """Own asynchronous local discovery without constructing a UI widget."""

    discovery_ready = Signal(object)
    discovery_failed = Signal(str)
    def __init__(
        self,
        discovery_fn: SlotDiscoveryFn = discover_save_slots,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.discovery_fn = discovery_fn
        self._slots: tuple[SaveSlot, ...] = ()
        self._searched_paths: tuple[Path, ...] = ()
        self._worker: SlotDiscoveryWorker | None = None
        self._refresh_pending = False

    @property
    def slots(self) -> tuple[SaveSlot, ...]:
        return self._slots

    @property
    def searched_paths(self) -> tuple[Path, ...]:
        return self._searched_paths

    def refresh(self) -> None:
        """Start one read-only discovery run; never open a slot implicitly."""

        if self._worker is not None and self._worker.isRunning():
            self._refresh_pending = True
            return
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
        self.discovery_failed.emit(message)

    def _on_worker_finished(self) -> None:
        self._worker = None
        if self._refresh_pending:
            self._refresh_pending = False
            self.refresh()

    def wait_for_worker(self, timeout_ms: int = 10_000) -> bool:
        """Wait for an in-flight discovery before the widget is destroyed."""

        worker = self._worker
        if worker is None:
            return True
        if worker.isRunning():
            worker.quit()
            if not worker.wait(timeout_ms):
                return False
        self._worker = None
        self._refresh_pending = False
        return True

    def _set_discovery(self, discovery: SaveDiscovery) -> None:
        self._slots = tuple(discovery.slots)
        self._searched_paths = tuple(Path(path) for path in discovery.searched_paths)


__all__ = [
    "GAME_IDS",
    "GAME_TITLES",
    "RELEASE_IDS",
    "RELEASE_TITLES",
    "SAVE_SUFFIXES",
    "SaveDiscovery",
    "SaveSlot",
    "SlotDiscoveryController",
    "SlotDiscoveryFn",
    "SlotDiscoveryWorker",
    "UnsupportedSaveReason",
    "_slot_family",
    "discover_save_slots",
]
