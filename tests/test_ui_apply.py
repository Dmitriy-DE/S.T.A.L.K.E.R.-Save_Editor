from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from editor.capabilities import CapabilitySupport, FormatCapabilities
from editor.models import EditPlan, PreparedEdit
from editor.service import EditorService
from save_format import SaveError, inspect_save
from ui.main_window import LocalSnapshot, MainWindow

# Generous on purpose: these cases drive real QThreads, and a loaded CI runner
# is slow, not broken.
UI_TIMEOUT_MS = 30_000


def _show_snapshot(window: MainWindow, source: Path, data: bytes) -> None:
    window._render_snapshot(
        LocalSnapshot(
            path=source,
            data=data,
            info=inspect_save(data, with_inventory=True),
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_money": CapabilitySupport("experimental"),
                    "edit_stacks": CapabilitySupport("experimental"),
                },
            ),
        )
    )


def test_preview_requires_staged_state_and_form_change_invalidates_preview(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "fixture.sav"
    source.write_bytes(synthetic_save)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    _show_snapshot(window, source, synthetic_save)

    assert not window.preview_button.isEnabled()
    window._stage_stack_change(0x30000001, 3)
    assert window.preview_button.isEnabled()
    window._start_preview()
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=UI_TIMEOUT_MS)
    # The action buttons settle when the worker thread exits, one tick after the
    # result arrives.  Waiting on the button is what a user actually does.
    qtbot.waitUntil(window.save_copy_button.isEnabled, timeout=UI_TIMEOUT_MS)
    prepared = window.prepared_edit

    window._stage_stack_change(0x30000001, 4)
    assert window.prepared_edit is None
    # One-click save stays available while there are staged changes — it will
    # re-run the internal preview on click; only the cached preview is invalid.
    assert window.save_copy_button.isEnabled()
    assert window.editor_view.detail_view.module_status.text().startswith(
        "Проверка перед сохранением сброшена"
    )
    assert prepared is not None


def test_double_click_apply_starts_one_export(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "fixture.sav"
    source.write_bytes(synthetic_save)
    output = tmp_path / "edited.sav"
    backup_dir = tmp_path / "backups"
    calls: list[tuple[Path, Path]] = []
    def prepare(data: bytes, plan: EditPlan) -> PreparedEdit:
        assert data == synthetic_save
        return PreparedEdit(plan=plan, data=data, output_sha256=hashlib.sha256(data).hexdigest())

    def export(source_path: Path, output_path: Path, prepared: PreparedEdit, backup: Path):
        calls.append((output_path, backup))
        time.sleep(0.05)
        return type(
            "Receipt",
            (),
            {
                "output_path": output_path,
                "backup_path": backup / "fixture_ORIGINAL.sav",
                "output_sha256": prepared.output_sha256,
            },
        )()

    window = MainWindow(EditorService(prepare_fn=prepare, export_fn=export))
    qtbot.addWidget(window)
    _show_snapshot(window, source, synthetic_save)
    window._stage_stack_change(0x30000001, 3)
    window._start_preview()
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=UI_TIMEOUT_MS)

    window._start_apply(output, backup_dir)
    window._start_apply(output, backup_dir)
    qtbot.waitSignal(window.apply_ready, timeout=UI_TIMEOUT_MS)
    qtbot.waitUntil(lambda: window._operation_thread is None, timeout=UI_TIMEOUT_MS)
    assert calls == [(output, backup_dir)]


def test_stale_preview_is_rejected_before_export(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "fixture.sav"
    source.write_bytes(synthetic_save)
    output = tmp_path / "edited.sav"
    backup_dir = tmp_path / "backups"
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    _show_snapshot(window, source, synthetic_save)
    window._stage_stack_change(0x30000001, 3)
    window._start_preview()
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=UI_TIMEOUT_MS)

    source.write_bytes(synthetic_save + b"changed after preview")
    with qtbot.waitSignal(window.operation_failed, timeout=UI_TIMEOUT_MS):
        window._start_apply(output, backup_dir)
    assert not output.exists()
    assert window.error_label.text() == (
        "Файл изменился после открытия. Открой его заново и повтори изменения."
    )
    assert window.error_label.toolTip() == ""
    details_button = next(
        button for button in window._error_dialog.buttons() if button.text() == "Подробнее"
    )
    details_button.click()
    assert window._details_dialog is not None
    assert "SHA" in window._details_dialog.text.toPlainText()


def test_worker_error_is_reported_and_close_does_not_abort_running_operation(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "fixture.sav"
    source.write_bytes(synthetic_save)
    started = threading.Event()
    release = threading.Event()

    def blocking_prepare(data: bytes, plan: EditPlan) -> PreparedEdit:
        started.set()
        release.wait(2)
        return PreparedEdit(plan=plan, data=data, output_sha256=hashlib.sha256(data).hexdigest())

    window = MainWindow(EditorService(prepare_fn=blocking_prepare))
    qtbot.addWidget(window)
    _show_snapshot(window, source, synthetic_save)
    window._stage_stack_change(0x30000001, 3)
    window._start_preview()
    qtbot.waitUntil(started.is_set, timeout=UI_TIMEOUT_MS)

    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    release.set()
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=UI_TIMEOUT_MS)

    def broken_prepare(data: bytes, plan: EditPlan) -> PreparedEdit:
        raise SaveError("injected preview failure")

    window.service = EditorService(prepare_fn=broken_prepare)
    window._stage_stack_change(0x30000001, 4)
    with qtbot.waitSignal(window.operation_failed, timeout=UI_TIMEOUT_MS):
        window._start_preview()
    assert window.error_label.text() == (
        "Попробуй ещё раз. Если проблема повторится, открой технические детали."
    )
    assert window.error_label.toolTip() == ""
    details_button = next(
        button for button in window._error_dialog.buttons() if button.text() == "Подробнее"
    )
    details_button.click()
    assert window._details_dialog is not None
    assert "injected preview failure" in window._details_dialog.text.toPlainText()


def test_one_click_save_confirms_once_then_replaces_open_slot_with_backup(
    qtbot, synthetic_save: bytes, tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "fixture.sav"
    source.write_bytes(synthetic_save)
    backup_dir = tmp_path / "backups"
    confirmations: list[tuple[str, str]] = []
    replaced: list[tuple[Path, Path]] = []

    def prepare(data: bytes, plan: EditPlan) -> PreparedEdit:
        return PreparedEdit(plan=plan, data=data, output_sha256=hashlib.sha256(data).hexdigest())

    def replace(source_path: Path, prepared: PreparedEdit, backup: Path):
        replaced.append((source_path, backup))
        return type(
            "Receipt",
            (),
            {"output_path": source_path, "backup_path": backup / "orig.sav",
             "output_sha256": prepared.output_sha256},
        )()

    def confirm(parent, title, text, buttons, default):
        confirmations.append((title, text))
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", staticmethod(confirm))
    monkeypatch.setattr("ui.main_window.backup_dirs", lambda: (backup_dir,))
    window = MainWindow(EditorService(prepare_fn=prepare, replace_fn=replace))
    qtbot.addWidget(window)
    _show_snapshot(window, source, synthetic_save)
    window._stage_stack_change(0x30000001, 3)

    # One click: the user confirms once; preview and replace stay internal.
    with qtbot.waitSignal(window.apply_ready, timeout=UI_TIMEOUT_MS):
        window._save_one_click()
    qtbot.waitUntil(lambda: window._operation_thread is None, timeout=UI_TIMEOUT_MS)

    assert len(confirmations) == 1
    assert confirmations[0][0] == "Сохранить изменения?"
    assert "резервная копия" in confirmations[0][1]
    assert replaced == [(source, backup_dir)]


def test_one_click_save_cancel_does_not_start_preview_or_write(
    qtbot, synthetic_save: bytes, tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "fixture.sav"
    source.write_bytes(synthetic_save)
    prepare_calls = 0
    replace_calls = 0

    def prepare(data: bytes, plan: EditPlan) -> PreparedEdit:
        nonlocal prepare_calls
        prepare_calls += 1
        return PreparedEdit(plan=plan, data=data, output_sha256=hashlib.sha256(data).hexdigest())

    def replace(source_path: Path, prepared: PreparedEdit, backup: Path):
        nonlocal replace_calls
        replace_calls += 1
        raise AssertionError("replace must not run after cancel")

    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.No),
    )
    window = MainWindow(EditorService(prepare_fn=prepare, replace_fn=replace))
    qtbot.addWidget(window)
    _show_snapshot(window, source, synthetic_save)
    window._stage_stack_change(0x30000001, 3)

    window._save_one_click()

    assert prepare_calls == 0
    assert replace_calls == 0
    assert window._operation_thread is None


def test_cloud_save_preview_failure_does_not_leave_upload_queued(
    qtbot, synthetic_save: bytes, tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "cloud-slot.sav"
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes),
    )
    window._render_snapshot(
        LocalSnapshot(
            path=source,
            data=synthetic_save,
            info=inspect_save(synthetic_save),
            source_kind="cloud",
            locator="Stalker2/Saved/STEAM/SaveGames/Data/cloud-slot.sav",
        )
    )
    window._stage_stack_change(0x30000001, 3)

    def broken_plan() -> EditPlan:
        raise SaveError("injected plan failure")

    monkeypatch.setattr(window, "_build_edit_plan", broken_plan)
    with qtbot.waitSignal(window.operation_failed, timeout=UI_TIMEOUT_MS):
        window._save_one_click()

    assert not window._pending_cloud_upload
