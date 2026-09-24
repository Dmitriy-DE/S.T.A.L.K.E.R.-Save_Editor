from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.service import EditorService
from save_format import inspect_save
from ui.character_view import CharacterView
from ui.main_window import LocalSnapshot, MainWindow


def test_character_surface_is_explicitly_read_only_without_verified_xray_catalog(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    view = CharacterView()
    qtbot.addWidget(view)
    view.set_snapshot(LocalSnapshot(
        path=tmp_path / "save.sav",
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
        release_id="stalker-soc",
        format_id="stalker-soc",
        format_title="Shadow of Chornobyl",
    ))

    assert view.objectName() == "characterView"
    assert view.faction_table.objectName() == "characterFactionTable"
    assert view.faction_table.rowCount() == 1
    assert view.faction_table.item(0, 0).text() == (
        "Данные о группировках недоступны для этого сохранения."
    )
    assert not view.player_faction_combo.isEnabled()


def test_s2_does_not_expose_character_editor(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(
        path=tmp_path / "save.sav",
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
        release_id="stalker2",
        format_id="stalker2",
    ))
    assert window.editor_view.character_button.isHidden()
