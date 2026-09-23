from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.service import EditorService
from ui.library_view import LibraryView
from ui.main_window import MainWindow
from ui.save_discovery import SaveDiscovery, SaveSlot


def _slot(path: Path, *, game_id: str, format_id: str | None = None, format_title: str | None = None) -> SaveSlot:
    return SaveSlot(
        path=path,
        candidate_game_id=game_id,
        candidate_game_title=game_id,
        size=128,
        modified_ns=1_700_000_000_000_000_000,
        format_id=format_id,
        format_title=format_title,
    )


def test_library_starts_with_all_games_and_import_path(qtbot) -> None:
    view = LibraryView()
    qtbot.addWidget(view)

    assert view.game_list.count() == 5
    first_game = view.game_list.item(0)
    assert first_game.text().startswith("ВСЕ ИГРЫ")
    assert not first_game.icon().isNull()
    assert view.game_list.item(1).text().startswith("S.T.A.L.K.E.R. 2")
    assert view.import_button.isEnabled()
    assert "ИМПОРТ" in view.import_button.text()


def test_library_filters_save_rows_and_opens_selected_slot(qtbot, tmp_path: Path) -> None:
    view = LibraryView()
    qtbot.addWidget(view)
    stalker2 = tmp_path / "stalker2.sav"
    cop = tmp_path / "cop.scop"
    view.set_installed_families({"stalker2"})
    view.set_discovery(
        SaveDiscovery(
            slots=(
                _slot(stalker2, game_id="stalker2", format_id="stalker2", format_title="S.T.A.L.K.E.R. 2: Heart of Chornobyl"),
                _slot(cop, game_id="cop"),
            ),
            searched_paths=(tmp_path,),
        )
    )

    assert view.save_table.rowCount() == 2
    assert "1 сохранений" in view.game_list.item(1).text()
    view.game_list.setCurrentRow(1)
    assert view.save_table.rowCount() == 1
    assert stalker2.name in view.save_table.item(0, 0).text()
    view.save_table.selectRow(0)

    with qtbot.waitSignal(view.open_requested, timeout=1_000) as blocker:
        view.open_selected()
    assert blocker.args == [stalker2]


def test_library_keeps_unknown_save_visible_and_marks_import_only_game(qtbot, tmp_path: Path) -> None:
    view = LibraryView()
    qtbot.addWidget(view)
    view.set_discovery(SaveDiscovery(slots=(), searched_paths=(tmp_path,)))

    assert view.save_table.rowCount() == 0
    assert "0 сохранений" in view.game_list.item(1).text()
    assert "ИМПОРТ" in view.import_button.text()


def test_main_window_starts_on_library_and_routes_global_cloud_destination(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)

    assert window.reference_stack.currentWidget() is window.library_view
    window._show_cloud()
    assert window.reference_stack.currentWidget() is window.cloud_reference_view
