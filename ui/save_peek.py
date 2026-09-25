"""Background read-only peek at a save for the library's quick summary.

Selecting a row in the save list should already show money, item count,
equipment and average condition.  The file is parsed on a worker thread
with the same service the editor uses; nothing is written and the result is
cached by path, size and modification time.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, QThreadPool, Signal

from editor.equipment import equipment_items

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


class _Signals(QObject):
    done = Signal(object, object)  # key, SavePeek | None


class _PeekTask(QRunnable):
    def __init__(self, key: tuple, path: Path, signals: _Signals) -> None:
        super().__init__()
        self._key = key
        self._path = path
        self._signals = signals

    def run(self) -> None:  # pragma: no cover - exercised through SavePeeker
        result = None
        try:
            from editor.service import EditorService

            data = self._path.read_bytes()
            inspection = EditorService().inspect_result(data, source_name=str(self._path))
            capabilities = inspection.capabilities
            editable = any(
                capabilities.support(name).writable
                for name in ("edit_money", "edit_stacks", "edit_durability")
            )
            result = summarize(
                inspection.info,
                release_id=str(inspection.release_id or inspection.format_id or ""),
                editable=editable,
                path=self._path,
            )
        except Exception:
            result = None
        try:
            self._signals.done.emit(self._key, result)
        except RuntimeError:
            pass  # the library closed while this file was being read


class SavePeeker(QObject):
    """Queue at most one peek per file; emit ``ready`` when it finishes."""

    ready = Signal(object)  # SavePeek

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache: dict[tuple, SavePeek | None] = {}
        self._pending: set[tuple] = set()
        self._signals = _Signals()
        self._signals.done.connect(self._finished)
        # Not a child: Qt must not delete the pool while a read is running.
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(1)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        self._pool.clear()
        self._pool.waitForDone(5000)

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
        if key is None or key in self._cache or key in self._pending:
            return
        self._pending.add(key)
        self._pool.start(_PeekTask(key, Path(path), self._signals))

    def _finished(self, key: tuple, result: SavePeek | None) -> None:
        self._pending.discard(key)
        self._cache[key] = result
        self.ready.emit(result)


__all__ = ["SavePeek", "SavePeeker", "summarize"]
