"""Run CPU-heavy read-only jobs in a child copy of the editor.

Parsing a 27 MB S.T.A.L.K.E.R. 2 save or unpacking a game archive is pure
Python; on a thread it holds the GIL and the window stutters.  The editor
therefore starts itself with a job flag (``--peek``, ``--extract-game-audio``)
and reads one JSON line from the child's stdout.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QProcess


def self_command(*arguments: str) -> tuple[str, list[str]]:
    """Program and arguments that start this editor in job mode."""

    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            # Inside a .app, the main executable owns the complete bundle
            # runtime. Relaunch it in CLI mode instead of guessing a sibling
            # helper path that may not be present in Contents/MacOS.
            return sys.executable, list(arguments)
        # The windowed Windows executable has no stdout; the console
        # companion shipped for Steam jobs does.
        native = Path(sys.executable).with_name("SaveEditor-native" + Path(sys.executable).suffix)
        program = str(native if native.is_file() else Path(sys.executable))
        return program, list(arguments)
    return sys.executable, ["-m", "ui", *arguments]


def emit_result(payload: object) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


class JsonJob(QObject):
    """One child job; ``callback`` receives the decoded JSON or ``None``."""

    def __init__(self, arguments: list[str], callback: Callable[[object], None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._callback = callback
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._failed)
        self._done = False
        program, args = self_command(*arguments)
        self._process.start(program, args)

    def kill(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(2000)

    def _deliver(self, value: object) -> None:
        if not self._done:
            self._done = True
            self._callback(value)
            self.deleteLater()

    def _failed(self, _error) -> None:
        if self._process.state() == QProcess.ProcessState.NotRunning:
            self._deliver(None)

    def _finished(self, exit_code: int, _status) -> None:
        output = bytes(self._process.readAllStandardOutput().data()).decode("utf-8", "replace")
        lines = [line for line in output.splitlines() if line.startswith(("{", "["))]
        value = None
        if exit_code == 0 and lines:
            try:
                value = json.loads(lines[-1])
            except ValueError:
                value = None
        self._deliver(value)


__all__ = ["JsonJob", "emit_result", "self_command"]
