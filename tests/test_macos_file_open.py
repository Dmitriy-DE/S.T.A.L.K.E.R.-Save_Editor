from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFileOpenEvent

from ui.application import SaveOpenEventRouter


def test_file_open_event_queues_local_save_until_window_handler_is_ready(
    tmp_path: Path,
) -> None:
    save_path = tmp_path / "slot.sav"
    router = SaveOpenEventRouter()
    opened: list[Path] = []

    assert router.receive(QFileOpenEvent(QUrl.fromLocalFile(str(save_path)))) is True
    assert opened == []

    router.set_handler(opened.append)

    assert opened == [save_path]


def test_file_open_event_dispatches_associated_save_to_ready_handler(tmp_path: Path) -> None:
    save_path = tmp_path / "slot.SCOP"
    router = SaveOpenEventRouter()
    opened: list[Path] = []
    router.set_handler(opened.append)

    assert router.receive(QFileOpenEvent(QUrl.fromLocalFile(str(save_path)))) is True

    assert opened == [save_path]


def test_file_open_event_ignores_unassociated_and_nonlocal_files(tmp_path: Path) -> None:
    router = SaveOpenEventRouter()
    opened: list[Path] = []
    router.set_handler(opened.append)

    assert router.receive(
        QFileOpenEvent(QUrl.fromLocalFile(str(tmp_path / "notes.txt")))
    ) is True
    assert router.receive(
        QFileOpenEvent(QUrl("https://example.test/slot.sav"))
    ) is True

    assert opened == []


def test_application_event_dispatches_file_open_to_window_handler(
    tmp_path: Path,
) -> None:
    save_path = tmp_path / "slot.sav"
    code = """
from pathlib import Path
import sys
from PySide6.QtCore import QUrl
from PySide6.QtGui import QFileOpenEvent
from ui.application import SaveEditorApplication

app = SaveEditorApplication([])
opened = []
app.set_save_open_handler(opened.append)
assert app.event(QFileOpenEvent(QUrl.fromLocalFile(sys.argv[1]))) is True
assert opened == [Path(sys.argv[1])], opened
"""

    subprocess.run(
        [sys.executable, "-c", code, str(save_path)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
