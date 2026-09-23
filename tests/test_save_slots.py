from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from editor.service import EditorService

pytest.importorskip("PySide6")

from ui.main_window import MainWindow
from ui.save_discovery import (
    SaveDiscovery,
    SlotDiscoveryController,
    UnsupportedSaveReason,
    discover_save_slots,
)


def test_discover_save_slots_sorts_newest_first_and_marks_unknown(
    synthetic_save: bytes, tmp_path: Path
) -> None:
    folders = {
        "stalker2": (tmp_path / "s2",),
        "cop": (tmp_path / "cop",),
        "clear_sky": (tmp_path / "cs",),
        "soc": (tmp_path / "soc",),
    }
    for folder in folders.values():
        folder[0].mkdir()
    newest = folders["stalker2"][0] / "newest.sav"
    middle = folders["cop"][0] / "middle.scop"
    oldest = folders["clear_sky"][0] / "oldest.scs"
    newest.write_bytes(synthetic_save)
    middle.write_bytes(b"foreign x-ray bytes")
    oldest.write_bytes(b"plain text")
    os.utime(newest, ns=(30, 3_000_000_000))
    os.utime(middle, ns=(20, 2_000_000_000))
    os.utime(oldest, ns=(10, 1_000_000_000))

    result = discover_save_slots(
        search_paths_fn=lambda game_id: folders[game_id],
    )

    assert [slot.path.name for slot in result.slots] == ["newest.sav", "middle.scop", "oldest.scs"]
    assert result.slots[0].format_id == "stalker2"
    assert result.slots[1].game_id is None
    assert "не распознано" in result.slots[1].status_text.casefold()
    assert result.searched_paths == tuple(path for values in folders.values() for path in values)


def test_discover_save_slots_includes_supported_foreign_suffixes(tmp_path: Path) -> None:
    folder = tmp_path / "cop"
    folder.mkdir()
    scop = folder / "quicksave.scop"
    scs = folder / "quicksave.scs"
    scop.write_bytes(b"foreign x-ray bytes")
    scs.write_bytes(b"unknown enhanced save")

    result = discover_save_slots(
        game_ids=("cop", "clear_sky"),
        search_paths_fn=lambda _game_id: (folder,),
    )

    assert {slot.path for slot in result.slots} == {scop, scs}


def test_discover_save_slots_explains_unavailable_enhanced_parser(tmp_path: Path) -> None:
    folder = tmp_path / "enhanced"
    folder.mkdir()
    path = folder / "quicksave.sav"
    path.write_bytes(b"unknown enhanced save")

    result = discover_save_slots(
        release_ids=("stalker-cs-ee",),
        search_paths_fn=lambda _release_id: (folder,),
    )

    assert result.slots[0].candidate_release_id == "stalker-cs-ee"
    assert result.slots[0].unsupported_reason == UnsupportedSaveReason(
        code="unsupported_release",
        message=(
            "Найден официальный сейв Enhanced Edition, но его формат "
            "ещё не подтверждён и не поддерживается"
        ),
    )


def test_discover_save_slots_reuses_detection_for_unchanged_file(tmp_path: Path) -> None:
    folder = tmp_path / "saves"
    folder.mkdir()
    path = folder / "slot.sav"
    path.write_bytes(b"synthetic")
    calls = 0

    def detector(_data: bytes):
        nonlocal calls
        calls += 1
        return None

    kwargs = {
        "game_ids": ("stalker2",),
        "search_paths_fn": lambda _game_id: (folder,),
        "detect_fn": detector,
    }
    discover_save_slots(**kwargs)
    discover_save_slots(**kwargs)
    assert calls == 1


def test_discovery_controller_publishes_result_and_waits_for_worker(qtbot, tmp_path: Path) -> None:
    started = threading.Event()

    def slow_discovery() -> SaveDiscovery:
        started.set()
        time.sleep(0.1)
        return SaveDiscovery((), (tmp_path,))

    controller = SlotDiscoveryController(slow_discovery)
    with qtbot.waitSignal(controller.discovery_ready, timeout=5_000) as signal:
        controller.refresh()
    assert started.is_set()
    assert signal.args[0].searched_paths == (tmp_path,)
    assert controller.wait_for_worker()
    assert controller._worker is None


def test_main_window_reports_missing_slot_as_open_error(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "vanished.sav"
    path.write_bytes(b"slot content")
    window = MainWindow(
        EditorService(),
        slot_discovery=lambda: SaveDiscovery((), (path.parent,)),
        auto_update_check=False,
    )
    qtbot.addWidget(window)
    path.unlink()

    with qtbot.waitSignal(window.analysis_failed, timeout=5_000):
        window._start_inspect(path)

    assert "vanished.sav" in window.error_label.text()
