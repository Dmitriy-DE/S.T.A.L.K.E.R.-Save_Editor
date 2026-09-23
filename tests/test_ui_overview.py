from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.service import EditorService
from save_format import inspect_save
from ui.main_window import LocalSnapshot, MainWindow


def _snapshot(synthetic_save: bytes, tmp_path: Path) -> LocalSnapshot:
    path = tmp_path / "slot.sav"
    path.write_bytes(synthetic_save)
    return LocalSnapshot(path=path, data=synthetic_save, info=inspect_save(synthetic_save))


def test_canonical_editor_uses_one_save_action_and_no_legacy_workbench(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)

    assert window.editor_view.save_button is window.save_copy_button
    assert not window.editor_view.save_button.isEnabled()
    assert not hasattr(window, "mode_stack")
    assert not hasattr(window, "workbench")
    assert not hasattr(window, "changes_view")


def test_editor_snapshot_is_parser_backed_and_xray_controls_are_conditional(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(_snapshot(synthetic_save, tmp_path))

    assert window.editor_view.item_count_label.text().endswith("2")
    assert "slot.sav" in window.editor_view.breadcrumb.text()
    assert window.editor_view.character_button.isHidden()

    xray = replace(_snapshot(synthetic_save, tmp_path), release_id="soc")
    window._render_snapshot(xray)
    assert not window.editor_view.character_button.isHidden()


def test_reference_frontend_has_only_global_destinations(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)

    assert tuple(window.app_shell.destination_names) == (
        "ЛОКАЛЬНЫЕ СОХРАНЕНИЯ",
        "STEAM CLOUD",
        "ИСТОРИЯ",
        "НАСТРОЙКИ",
    )
    assert window.reference_stack.count() == 9
