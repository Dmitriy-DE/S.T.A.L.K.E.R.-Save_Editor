from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.service import EditorService
from save_format import inspect_save
from ui.backups_view import BackupView
from ui.character_view import CharacterView
from ui.cloud_library_view import CloudLibraryView
from ui.history_view import HistoryView
from ui.main_window import LocalSnapshot, MainWindow
from ui.save_result_view import SaveResultView
from ui.save_review import SaveReviewView
from ui.unsupported_view import UnsupportedView


def test_reference_stack_has_global_cloud_and_history_states(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)

    names = {
        window.reference_stack.widget(index).objectName()
        for index in range(window.reference_stack.count())
    }
    assert {"cloudLibraryView", "historyView", "settingsView"}.issubset(names)
    assert tuple(window.app_shell.destination_names) == (
        "ЛОКАЛЬНЫЕ СОХРАНЕНИЯ",
        "STEAM CLOUD",
        "ИСТОРИЯ",
        "НАСТРОЙКИ",
    )


def test_cloud_surface_exposes_read_only_gate_and_explicit_actions(qtbot) -> None:
    backend = __import__("ui.cloud_view", fromlist=["CloudView"]).CloudView(
        EditorService(), helper_finder=lambda: None
    )
    view = CloudLibraryView(backend)
    qtbot.addWidget(view)

    assert view.objectName() == "cloudLibraryView"
    assert view.save_table is not None
    assert view.download_button.text().startswith("СКАЧАТЬ")
    assert view.upload_button.isEnabled() is False
    assert "только" in view.read_only_banner.text().casefold()


def test_history_surface_keeps_restore_disabled_until_verified_preview(qtbot, tmp_path: Path) -> None:
    backend = BackupView(backup_dirs=(tmp_path,))
    view = HistoryView(backend)
    qtbot.addWidget(view)

    assert view.objectName() == "historyView"
    assert not view.restore_button.isEnabled()
    assert not view.restore_in_place_button.isEnabled()
    assert view.detail_panel.objectName() == "historyDetailPanel"


def test_character_state_is_xray_only_and_has_faction_region(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    view = CharacterView()
    qtbot.addWidget(view)
    snapshot = LocalSnapshot(
        path=tmp_path / "save.sav",
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
        format_id="soc",
        release_id="soc",
        format_title="Shadow of Chornobyl",
    )
    view.set_snapshot(snapshot)

    assert view.objectName() == "characterView"
    assert view.faction_table.objectName() == "characterFactionTable"
    assert view.back_button.text().startswith("НАЗАД")
    assert view.editable is False


def test_review_result_and_unsupported_states_are_explicit(qtbot) -> None:
    review = SaveReviewView()
    result = SaveResultView()
    unsupported = UnsupportedView()
    for widget in (review, result, unsupported):
        qtbot.addWidget(widget)

    assert review.changes_table.objectName() == "reviewChangesTable"
    assert review.pipeline_steps.objectName() == "reviewPipelineSteps"
    assert review.confirm_button.text().startswith("СОХРАНИТЬ")
    assert result.receipt_table.objectName() == "resultReceiptTable"
    assert unsupported.writer_label.objectName() == "unsupportedWriterLabel"
    assert not hasattr(unsupported, "save_button")


def test_main_window_routes_staged_save_through_visible_review(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    snapshot = LocalSnapshot(
        path=tmp_path / "save.sav",
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
    )
    window._render_snapshot(snapshot)
    window.staged_counts[0x30000001] = 3
    window._render_changes()
    window._request_reference_save()

    assert window.reference_stack.currentWidget() is window.save_review_view
    assert window.save_review_view.changes_table.rowCount() == 1


def test_review_route_survives_previous_global_destination(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    snapshot = LocalSnapshot(
        path=tmp_path / "save.sav",
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
    )
    window._render_snapshot(snapshot)
    window._show_history()
    window.staged_counts[0x30000001] = 3
    window._render_changes()
    window._request_reference_save()

    assert window.reference_stack.currentWidget() is window.save_review_view
