"""Workbench quick game+save switcher."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.service import EditorService
from ui.main_window import MainWindow
from ui.save_slots_view import SaveDiscovery, SaveSlot


def _slot(path: Path, family: str) -> SaveSlot:
    return SaveSlot(
        path=path,
        candidate_game_id=family,
        candidate_game_title=family,
        size=1,
        modified_ns=0,
    )


def _settle(win: MainWindow) -> None:
    # MainWindow starts a background save-discovery worker; let it finish so it
    # never outlives the widget and crashes Qt teardown on Windows.
    try:
        win.save_slots_view.wait_for_worker()
    except Exception:
        pass


def test_switcher_populates_and_opens(qtbot, tmp_path, monkeypatch):
    win = MainWindow(EditorService())
    qtbot.addWidget(win)
    _settle(win)
    a = tmp_path / "cs1.sav"
    a.write_bytes(b"x")
    win._populate_switcher(SaveDiscovery((_slot(a, "clear_sky"),), ()))

    assert win.switcher_game_combo.count() == 1
    assert win.switcher_save_combo.count() == 1
    assert win.switcher_open_button.isEnabled()

    opened: dict[str, Path] = {}
    monkeypatch.setattr(win, "_start_inspect", lambda p: opened.__setitem__("p", p))
    win._open_switcher_selection()
    assert opened["p"] == a


def test_switcher_empty_discovery_disables_open(qtbot):
    win = MainWindow(EditorService())
    qtbot.addWidget(win)
    _settle(win)
    win._populate_switcher(SaveDiscovery((), ()))
    assert win.switcher_game_combo.count() == 0
    assert not win.switcher_open_button.isEnabled()
