"""Application-level handling for files opened by the operating system."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import QEvent
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QApplication

SaveOpenHandler = Callable[[Path], None]


class SaveOpenEventRouter:
    """Route associated local save files to the UI, queueing early events."""

    def __init__(self) -> None:
        self._handler: SaveOpenHandler | None = None
        self._pending: list[Path] = []

    def set_handler(self, handler: SaveOpenHandler) -> None:
        self._handler = handler
        pending, self._pending = self._pending, []
        for path in pending:
            handler(path)

    def receive(self, event: QEvent) -> bool:
        if event.type() != QEvent.Type.FileOpen:
            return False

        path = self._associated_save_path(cast(QFileOpenEvent, event))
        if path is not None:
            if self._handler is None:
                self._pending.append(path)
            else:
                self._handler(path)
        return True

    @staticmethod
    def _associated_save_path(event: QFileOpenEvent) -> Path | None:
        url = event.url()
        if not url.isLocalFile():
            return None
        path = Path(url.toLocalFile())
        if path.suffix.casefold() not in {".sav", ".scop"}:
            return None
        return path


class SaveEditorApplication(QApplication):
    """Qt application that handles Finder/Open With file-open events."""

    def __init__(self, arguments: list[str]) -> None:
        self._save_open_router = SaveOpenEventRouter()
        super().__init__(arguments)

    def set_save_open_handler(self, handler: SaveOpenHandler) -> None:
        self._save_open_router.set_handler(handler)

    def event(self, event: QEvent) -> bool:
        if self._save_open_router.receive(event):
            return True
        return super().event(event)


__all__ = ["SaveEditorApplication", "SaveOpenEventRouter"]
