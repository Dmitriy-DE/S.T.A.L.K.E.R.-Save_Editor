from __future__ import annotations

import os
from pathlib import Path

import pytest

from editor.service import EditorService

pytest.importorskip("PySide6")

from ui.main_window import MainWindow
from ui.save_slots_view import (
    SaveDiscovery,
    SaveSlot,
    SaveSlotsView,
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
    middle = folders["cop"][0] / "middle.sav"
    oldest = folders["clear_sky"][0] / "oldest.sav"
    newest.write_bytes(synthetic_save)
    middle.write_bytes(b"foreign x-ray bytes")
    oldest.write_bytes(b"plain text")
    os.utime(newest, ns=(30, 3_000_000_000))
    os.utime(middle, ns=(20, 2_000_000_000))
    os.utime(oldest, ns=(10, 1_000_000_000))

    def search_paths(game_id: str) -> tuple[Path, ...]:
        return folders[game_id]

    result = discover_save_slots(search_paths_fn=search_paths)

    assert [slot.path.name for slot in result.slots] == [
        "newest.sav",
        "middle.sav",
        "oldest.sav",
    ]
    assert result.slots[0].format_id == "stalker2"
    assert result.slots[0].game_id == "stalker2"
    assert result.slots[1].format_id is None
    assert result.slots[1].game_id is None
    assert "не распознано" in result.slots[1].status_text.casefold()
    assert result.searched_paths == tuple(path for values in folders.values() for path in values)


def test_discover_save_slots_includes_call_of_pripyat_scop_files(tmp_path: Path) -> None:
    folder = tmp_path / "cop"
    folder.mkdir()
    path = folder / "quicksave.scop"
    path.write_bytes(b"foreign x-ray bytes")

    result = discover_save_slots(
        game_ids=("cop",),
        search_paths_fn=lambda _game_id: (folder,),
    )

    assert [slot.path for slot in result.slots] == [path]


def test_discover_save_slots_surfaces_enhanced_scs_candidates(tmp_path: Path) -> None:
    folder = tmp_path / "enhanced"
    folder.mkdir()
    path = folder / "quicksave.scs"
    path.write_bytes(b"unknown enhanced save")

    result = discover_save_slots(
        game_ids=("clear_sky",),
        search_paths_fn=lambda _game_id: (folder,),
    )

    assert [slot.path for slot in result.slots] == [path]
    assert result.slots[0].format_id is None
    assert result.slots[0].candidate_release_id == "clear_sky"
    assert result.slots[0].unsupported_reason == UnsupportedSaveReason(
        code="unknown_format",
        message="Не распознано зарегистрированным форматом",
    )


def test_discover_save_slots_records_release_metadata_for_detected_content(
    synthetic_save: bytes, tmp_path: Path
) -> None:
    folder = tmp_path / "saves"
    folder.mkdir()
    path = folder / "slot.sav"
    path.write_bytes(synthetic_save)

    result = discover_save_slots(
        release_ids=("stalker2",),
        search_paths_fn=lambda _release_id: (folder,),
    )

    slot = result.slots[0]
    assert slot.candidate_release_id == "stalker2"
    assert slot.detected_release_id == "stalker2"
    assert slot.unsupported_reason is None


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


def test_save_slots_view_renders_rows_and_emits_explicit_open(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    path = tmp_path / "slot.sav"
    path.write_bytes(synthetic_save)
    slot = SaveSlot(
        path=path,
        candidate_game_id="stalker2",
        candidate_game_title="S.T.A.L.K.E.R. 2: Heart of Chornobyl",
        size=path.stat().st_size,
        modified_ns=path.stat().st_mtime_ns,
        format_id="stalker2",
        format_title="S.T.A.L.K.E.R. 2: Heart of Chornobyl",
    )
    view = SaveSlotsView(
        discovery_fn=lambda: SaveDiscovery((slot,), (tmp_path / "missing",))
    )
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.discovery_ready, timeout=5_000):
        view.refresh()

    assert view.table.rowCount() == 1
    name_item = view.table.item(0, 0)
    status_item = view.table.item(0, 3)
    assert name_item is not None
    assert status_item is not None
    assert name_item.text() == "slot.sav"
    assert "S.T.A.L.K.E.R. 2" in status_item.text()
    with qtbot.waitSignal(view.open_requested, timeout=1_000) as signal:
        view._open_row(0, 0)
    assert signal.args == [path]


def test_save_slots_view_empty_result_is_informational(qtbot, tmp_path: Path) -> None:
    searched = (tmp_path / "first", tmp_path / "second")
    view = SaveSlotsView(discovery_fn=lambda: SaveDiscovery((), searched))
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.discovery_ready, timeout=5_000):
        view.refresh()

    assert view.table.rowCount() == 0
    assert "не ошибка" in view.empty_label.text().casefold()
    for path in searched:
        assert str(path) in view.search_paths_label.text()


def test_main_window_reports_missing_slot_as_open_error(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "vanished.sav"
    path.write_bytes(b"slot content")
    stat = path.stat()
    slot = SaveSlot(
        path=path,
        candidate_game_id="stalker2",
        candidate_game_title="S.T.A.L.K.E.R. 2: Heart of Chornobyl",
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        detection_error="synthetic unknown",
    )
    window = MainWindow(
        EditorService(),
        slot_discovery=lambda: SaveDiscovery((slot,), (path.parent,)),
    )
    qtbot.addWidget(window)
    path.unlink()

    with qtbot.waitSignal(window.analysis_failed, timeout=5_000):
        window.save_slots_view.open_requested.emit(path)

    assert "vanished.sav" in window.error_label.text()
