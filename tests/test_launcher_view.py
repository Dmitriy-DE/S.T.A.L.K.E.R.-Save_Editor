from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.service import EditorService
from ui.launcher_view import LauncherView
from ui.main_window import MainWindow
from ui.save_slots_view import SaveDiscovery, SaveSlot


def _slot(
    path: Path,
    *,
    game_id: str,
    format_id: str | None = None,
    format_title: str | None = None,
) -> SaveSlot:
    return SaveSlot(
        path=path,
        candidate_game_id=game_id,
        candidate_game_title=game_id,
        size=128,
        modified_ns=1_700_000_000_000_000_000,
        format_id=format_id,
        format_title=format_title,
    )


def test_launcher_starts_with_all_games_and_import_path(qtbot) -> None:
    view = LauncherView()
    qtbot.addWidget(view)

    assert view.game_list.count() == 5
    assert view.game_list.item(0).text() == "ВСЕ ИГРЫ"
    assert view.game_list.item(1).text().startswith("S.T.A.L.K.E.R. 2")
    assert view.import_button.isEnabled()
    assert "импорт" in view.status_label.text().casefold()


def test_launcher_filters_save_library_and_opens_selected_slot(qtbot, tmp_path: Path) -> None:
    view = LauncherView()
    qtbot.addWidget(view)
    stalker2 = tmp_path / "stalker2.sav"
    cop = tmp_path / "cop.scop"
    view.set_installed_families({"stalker2"})
    view.set_discovery(
        SaveDiscovery(
            slots=(
                _slot(
                    stalker2,
                    game_id="stalker2",
                    format_id="stalker2",
                    format_title="S.T.A.L.K.E.R. 2: Heart of Chornobyl",
                ),
                _slot(cop, game_id="cop"),
            ),
            searched_paths=(tmp_path,),
        )
    )

    assert view.save_table.rowCount() == 2
    assert "УСТАНОВЛЕНА" in view.game_list.item(1).text()

    view.game_list.setCurrentRow(1)
    assert view.save_table.rowCount() == 1
    assert view.save_table.item(0, 0).text() == stalker2.name
    view.save_table.selectRow(0)

    with qtbot.waitSignal(view.open_requested, timeout=1_000) as blocker:
        view.open_selected()
    assert blocker.args == [stalker2]


def test_launcher_keeps_unknown_save_visible_and_marks_import_only_game(qtbot, tmp_path: Path) -> None:
    view = LauncherView()
    qtbot.addWidget(view)
    view.set_discovery(SaveDiscovery(slots=(), searched_paths=(tmp_path,)))

    assert view.save_table.rowCount() == 0
    assert "НЕ НАЙДЕНА" in view.game_list.item(1).text()
    assert "импорт" in view.game_list.item(1).text().casefold()


def test_main_window_uses_launcher_until_a_save_is_opened(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "downloaded-stalker2.sav"
    source.write_bytes(synthetic_save)
    window = MainWindow(
        EditorService(),
        slot_discovery=lambda: SaveDiscovery((), (tmp_path,)),
    )
    qtbot.addWidget(window)

    assert window.mode_stack.currentWidget() is window.launcher_view
    assert window.launcher_view.game_list.count() == 5

    with qtbot.waitSignal(window.analysis_ready, timeout=5_000):
        window._start_inspect(source)

    assert window.mode_stack.currentWidget() is window.workbench
