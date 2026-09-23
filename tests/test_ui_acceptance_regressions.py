from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QWidget

from editor.models import CloudReceipt, EditPlan, PreparedEdit, SourceRef
from editor.releases import is_xray_original_release
from editor.service import EditorService
from editor.storage import BackupRecord, ExportReceipt
from editor.xray_save import COP_FORMAT, inspect_xray
from save_format import inspect_save
from steam_cloud import CloudFile
from ui.cloud_controller import CloudController, CloudSnapshot
from ui.main_window import LocalSnapshot, MainWindow
from ui.save_discovery import SaveDiscovery, SaveSlot
from ui.save_result_view import SaveResultView


@pytest.mark.parametrize("release_id", ("stalker-soc", "stalker-cs", "stalker-cop"))
def test_official_xray_release_ids_expose_character_route(
    qtbot, synthetic_save: bytes, tmp_path: Path, release_id: str
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    snapshot = LocalSnapshot(
        path=tmp_path / f"{release_id}.sav",
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
        release_id=release_id,
        format_id=release_id,
        format_title=release_id,
    )
    window._render_snapshot(snapshot)

    assert is_xray_original_release(release_id)
    assert not window.editor_view.character_button.isHidden()


def test_s2_release_does_not_expose_character_route(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "stalker2.sav",
            data=synthetic_save,
            info=inspect_save(synthetic_save, with_inventory=True),
            release_id="stalker2",
            format_id="stalker2",
        )
    )

    assert not is_xray_original_release("stalker2")
    assert window.editor_view.character_button.isHidden()


@pytest.mark.parametrize("index", range(7))
def test_settings_category_indices_use_one_canonical_order(qtbot, index: int) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    view = window.settings_reference_view

    assert tuple(view.settings_stack._pages) == tuple(view._settings_pages)
    view.category_buttons[index].click()
    assert view.settings_stack.currentWidget() is view._settings_pages[index]


def _visible_text(window: MainWindow) -> str:
    values: list[str] = []
    for widget in window.findChildren(QWidget):
        if not widget.isVisible():
            continue
        text = getattr(widget, "text", None)
        if callable(text):
            value = text()
            if value:
                values.append(str(value))
    return "\n".join(values)


def test_visible_normal_workflow_has_no_internal_stage_or_preview_terms(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "stalker-soc.sav",
            data=synthetic_save,
            info=inspect_save(synthetic_save, with_inventory=True),
            release_id="stalker-soc",
            format_id="stalker-soc",
        )
    )
    forbidden = re.compile(r"staged|stage|застейджить|preview", re.IGNORECASE)
    for show_screen in (
        window._show_reference_library,
        window._show_reference_editor,
        window._show_cloud,
        window._show_history,
        window._show_settings,
        window._show_character_state,
    ):
        show_screen()
        qtbot.wait(5)
        assert not forbidden.search(_visible_text(window)), show_screen.__name__


def test_money_edit_updates_shared_draft_without_field_apply_button(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "fixture.sav",
            data=synthetic_save,
            info=inspect_save(synthetic_save, with_inventory=True),
        )
    )

    assert not hasattr(window.editor_view, "money_stage_button")
    window.editor_view.money_spin.setValue(900)
    assert window.staged_money == 900
    assert window.editor_view.save_button.text() == "СОХРАНИТЬ 1 ИЗМЕНЕНИЙ"


def test_analysis_failure_is_attached_and_does_not_route_to_editor(
    qtbot, tmp_path: Path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.show()
    window._start_inspect(tmp_path / "missing.sav")
    qtbot.waitUntil(lambda: window.error_label.isVisible(), timeout=3000)

    assert window.reference_stack.currentWidget() is window.library_view
    assert window.error_label.parent() is window.library_view
    assert "missing.sav" in window.error_label.text()


def test_verified_local_save_reinspects_written_slot_and_clears_draft(
    qtbot, tmp_path: Path
) -> None:
    from test_xray_save import _fixture

    data = _fixture()
    output = tmp_path / "written.scop"
    output.write_bytes(data)
    info = inspect_xray(data, COP_FORMAT)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "source.scop",
            data=data,
            info=info,
            format_id=COP_FORMAT.id,
            format_title=COP_FORMAT.title,
            release_id=COP_FORMAT.id,
            edition="original",
        )
    )
    window.staged_counts[info.inventory[0].handle] = 3
    window._render_changes()
    receipt = ExportReceipt(
        output_path=output,
        backup_path=tmp_path / "backup.sav",
        output_sha256=hashlib.sha256(data).hexdigest(),
    )

    window._operation_kind = "replace"
    window._on_apply_ready(receipt)
    qtbot.waitUntil(lambda: window._post_save_reinspect_thread is None, timeout=5000)

    assert window.snapshot is not None
    assert window.snapshot.path == output
    assert window.snapshot.info.sha256 == hashlib.sha256(data).hexdigest()
    assert window.staged_counts == {}
    assert window.staged_money is None
    assert window.editor_view.save_button.text() == "СОХРАНИТЬ 0 ИЗМЕНЕНИЙ"
    assert not window.editor_view.save_button.isEnabled()
    assert tuple(window.editor_view.model.source_items) == tuple(window.snapshot.info.inventory)
    assert window.library_view._snapshot is window.snapshot
    window.save_result_view.editor_button.click()
    assert window.reference_stack.currentWidget() is window.editor_view
    assert not window.editor_view.save_button.isEnabled()


def test_footer_actions_are_real_shortcuts(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(20)

    window._show_reference_library()
    assert {action.key for action in window.app_shell.footer_actions} >= {"Enter", "I", "R", "F"}
    assert all(action.shortcut is not None for action in window.app_shell.footer_actions)
    filter_action = next(action for action in window.app_shell.footer_actions if action.key == "F")
    filter_action.shortcut.activated.emit()
    assert filter_action.shortcut.key().toString() == "F"
    assert filter_action.callback.__self__ is window.library_view.search_edit
    assert filter_action.callback.__name__ == "setFocus"

    window._show_settings()
    next(action for action in window.app_shell.footer_actions if action.key == "D").shortcut.activated.emit()
    assert window.settings_reference_view.category_buttons[0].isChecked()


def _cloud_receipt(tmp_path: Path, *, status: str, sha: str, reason: str | None = None) -> CloudReceipt:
    return CloudReceipt(
        status=status,  # type: ignore[arg-type]
        remote_path="slot.sav",
        backup_path=tmp_path / "cloud-original.sav",
        recovery_path=tmp_path / "cloud-edited.sav",
        output_sha256=sha,
        reason=reason,
    )


def test_verified_cloud_result_requires_remote_reconciliation(qtbot, tmp_path: Path, synthetic_save: bytes) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    controller = CloudController(EditorService(), helper_finder=lambda: None)
    prepared = PreparedEdit(
        plan=EditPlan(source=SourceRef("cloud", "slot.sav", info.sha256)),
        data=synthetic_save,
        output_sha256=info.sha256,
    )
    controller._prepared = prepared
    receipt = _cloud_receipt(tmp_path, status="verified", sha=info.sha256)
    controller._on_upload_ready(receipt)

    assert controller.reconciliation_pending
    assert controller.reconciliation_status == "pending"
    assert controller._prepared is prepared

    file = CloudFile("slot.sav", len(synthetic_save), 1, True, True)
    controller._on_snapshot_ready(
        CloudSnapshot(
            name="slot.sav",
            data=synthetic_save,
            info=info,
            file=file,
        )
    )
    assert controller.reconciliation_status == "verified"
    assert not controller.reconciliation_pending
    assert controller._prepared is None


def test_uncertain_cloud_result_exposes_reconcile_without_retry(qtbot, tmp_path: Path) -> None:
    view = SaveResultView()
    qtbot.addWidget(view)
    view.show()
    receipt = _cloud_receipt(tmp_path, status="uncertain", sha="a" * 64, reason="timeout")
    view.set_receipt(receipt)

    assert view.reconcile_button.isVisible()
    assert not view.editor_button.isEnabled()
    assert "ОБНОВИТЬ STEAM CLOUD" in view.reconcile_button.text()
    assert "Повторная запись" in view.subtitle.text()


def test_recent_activity_is_updated_from_session_operation(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._record_recent_activity("Локальное сохранение", "/tmp/slot.sav", "SHA abc…")

    assert "Локальное сохранение" in window.library_view.activity_label.text()
    assert "/tmp/slot.sav" in window.library_view.activity_label.text()


def test_library_restore_routes_to_matching_history_record(qtbot, tmp_path: Path) -> None:
    source = tmp_path / "autosave.sav"
    backup = tmp_path / "autosave.ORIGINAL.sav"
    journal = tmp_path / "autosave.json"
    record = BackupRecord(
        journal_path=journal,
        backup_path=backup,
        created_at="2026-09-23 01:00:00",
        source_path=str(source),
        source_sha256="a" * 64,
        output_path=str(source),
        output_sha256="b" * 64,
        operation={"mode": "replace"},
        status="verified",
        actual_sha256="a" * 64,
    )
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.backup_controller.set_review_records((record,))
    window.library_view.set_discovery(
        SaveDiscovery(
            slots=(SaveSlot(source, "stalker2", "S.T.A.L.K.E.R. 2", 10, 1),),
            searched_paths=(tmp_path,),
        )
    )
    window.library_view.restore_button.click()

    assert window.reference_stack.currentWidget() is window.history_reference_view
    assert window.history_reference_view.source_filter_edit.text() == source.name
    assert window.history_reference_view.table.currentRow() == 0


def test_frameless_chrome_exposes_working_window_controls(qtbot) -> None:
    from PySide6.QtCore import Qt

    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    window.app_shell.minimize_button.click()
    window.showNormal()
    window.app_shell.maximize_button.click()
    assert window.isMaximized()
    window.app_shell.maximize_button.click()
    assert not window.isMaximized()
