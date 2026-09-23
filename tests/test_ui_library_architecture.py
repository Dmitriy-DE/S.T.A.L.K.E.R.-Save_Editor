from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QTableWidget

from ui.library_view import LibraryView


def test_library_has_canonical_three_region_surface(qtbot) -> None:
    view = LibraryView()
    qtbot.addWidget(view)

    assert view.objectName() == "libraryView"
    assert view.game_rail.objectName() == "libraryGameRail"
    assert view.save_table.objectName() == "librarySaveTable"
    assert isinstance(view.save_table, QTableWidget)
    assert view.preview_panel.objectName() == "libraryPreviewPanel"
    assert view.recent_activity.objectName() == "libraryRecentActivity"
    assert view.open_button.text().startswith("ОТКРЫТЬ СОХРАНЕНИЕ")
    assert view.import_button.text() == "ИМПОРТИРОВАТЬ…"


def test_library_filter_and_open_are_real_signals(qtbot, tmp_path) -> None:
    view = LibraryView()
    qtbot.addWidget(view)
    view.search_edit.setText("slot")
    assert view.search_edit.text() == "slot"

    with qtbot.waitSignal(view.import_requested, timeout=1_000):
        view.import_button.click()

    assert view.refresh_button.isEnabled()
