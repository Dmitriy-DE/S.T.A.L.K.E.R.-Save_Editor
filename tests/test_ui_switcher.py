from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.service import EditorService
from ui.main_window import MainWindow
from ui.save_discovery import SaveDiscovery, SaveSlot


def test_discovery_controller_populates_canonical_library(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "slot.sav"
    slot = SaveSlot(
        path=path,
        candidate_game_id="clear_sky",
        candidate_game_title="Clear Sky",
        size=1,
        modified_ns=0,
    )
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.discovery_controller._set_discovery(SaveDiscovery((slot,), (tmp_path,)))
    window.library_view.set_discovery(SaveDiscovery((slot,), (tmp_path,)))

    assert window.library_view.save_table.rowCount() == 1
    assert path.name in window.library_view.save_table.item(0, 0).text()


def test_discovery_controller_is_read_only_and_does_not_auto_open(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    assert window.snapshot is None
    assert window.reference_stack.currentWidget() is window.library_view
