"""Background read-only peek at a save for the library's quick summary.

Selecting a row in the save list should already show money, item count,
equipment and average condition.  The file is parsed on a worker thread
with the same service the editor uses; nothing is written and the result is
cached by path, size and modification time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Signal

from editor.equipment import equipment_items

from .worker_process import JsonJob

_EQUIPMENT = frozenset({"weapon", "armor", "helmet", "device"})


@dataclass(frozen=True)
class SavePeek:
    path: Path
    money: int | None
    items: int
    equipment: int
    condition: float | None
    release_id: str
    crc_ok: bool
    editable: bool


def summarize(info, *, release_id: str, editable: bool, path: Path) -> SavePeek:
    rows = equipment_items(info.inventory, release_id=release_id)
    conditions = [item.condition for item in info.inventory if item.condition is not None]
    return SavePeek(
        path=path,
        money=info.money,
        items=len(info.inventory),
        equipment=sum(1 for row in rows if row.category in _EQUIPMENT),
        condition=(sum(conditions) / len(conditions)) if conditions else None,
        release_id=release_id,
        crc_ok=bool(info.crc_ok),
        editable=editable,
    )


def peek_path(path: Path) -> SavePeek | None:
    """Read one save and summarize it (runs in the ``--peek`` child)."""

    from editor.service import EditorService

    data = Path(path).read_bytes()
    inspection = EditorService().inspect_result(data, source_name=str(path))
    capabilities = inspection.capabilities
    editable = any(
        capabilities.support(name).writable
        for name in ("edit_money", "edit_stacks", "edit_durability")
    )
    return summarize(
        inspection.info,
        release_id=str(inspection.release_id or inspection.format_id or ""),
        editable=editable,
        path=Path(path),
    )


def peek_main(arguments: list[str]) -> int:
    """``--peek <path>``: print the summary as one JSON line."""

    from .worker_process import emit_result

    try:
        peek = peek_path(Path(arguments[0]))
    except Exception:
        peek = None
    if peek is None:
        return emit_result(None)
    payload = asdict(peek)
    payload["path"] = str(peek.path)
    return emit_result(payload)


def _from_payload(payload: object) -> SavePeek | None:
    if not isinstance(payload, dict):
        return None
    try:
        return SavePeek(**{**payload, "path": Path(str(payload["path"]))})
    except (TypeError, KeyError):
        return None


class SavePeeker(QObject):
    """Peek one file at a time in a child process; the newest request wins."""

    ready = Signal(object)  # SavePeek | None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache: dict[tuple, SavePeek | None] = {}
        self._running: tuple | None = None
        self._job: JsonJob | None = None
        self._queued: tuple[tuple, Path] | None = None
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        self._queued = None
        if self._job is not None:
            self._job.kill()

    @staticmethod
    def _key(path: Path) -> tuple | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return (str(path.resolve()), stat.st_size, stat.st_mtime_ns)

    def cached(self, path: Path) -> SavePeek | None:
        key = self._key(path)
        return self._cache.get(key) if key is not None else None

    def failed(self, path: Path) -> bool:
        key = self._key(path)
        return key is None or (key in self._cache and self._cache[key] is None)

    def request(self, path: Path) -> None:
        key = self._key(path)
        if key is None or key in self._cache or key == self._running:
            return
        if self._running is not None:
            self._queued = (key, Path(path))  # only the latest selection matters
            return
        self._start(key, Path(path))

    def _start(self, key: tuple, path: Path) -> None:
        self._running = key
        self._job = JsonJob(["--peek", str(path)], lambda payload: self._finished(key, payload), self)

    def _finished(self, key: tuple, payload: object) -> None:
        self._running = None
        self._job = None
        result = _from_payload(payload)
        self._cache[key] = result
        self.ready.emit(result)
        if self._queued is not None:
            queued_key, queued_path = self._queued
            self._queued = None
            if queued_key not in self._cache:
                self._start(queued_key, queued_path)


__all__ = ["SavePeek", "SavePeeker", "peek_main", "peek_path", "summarize"]
