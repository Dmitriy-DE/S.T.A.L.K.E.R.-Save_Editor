from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QCloseEvent

from editor.models import EditPlan, PreparedEdit, SourceRef
from editor.service import EditorService
from save_format import SaveError, inspect_save
from ui.main_window import LocalSnapshot, MainWindow


def _show_snapshot(window: MainWindow, source: Path, data: bytes) -> None:
    window._render_snapshot(
        LocalSnapshot(path=source, data=data, info=inspect_save(data, with_inventory=True))
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
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=5_000)
    assert window.save_copy_button.isEnabled()
    prepared = window.prepared_edit

    window._stage_stack_change(0x30000001, 4)
    assert window.prepared_edit is None
    assert not window.save_copy_button.isEnabled()
    assert window.changes_view.preview_status_label.text().startswith("Preview недействителен")
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
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=5_000)

    window._start_apply(output, backup_dir)
    window._start_apply(output, backup_dir)
    qtbot.waitSignal(window.apply_ready, timeout=5_000)
    qtbot.waitUntil(lambda: window._operation_thread is None, timeout=5_000)
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
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=5_000)

    source.write_bytes(synthetic_save + b"changed after preview")
    with qtbot.waitSignal(window.operation_failed, timeout=5_000):
        window._start_apply(output, backup_dir)
    assert not output.exists()
    assert "SHA256" in window.error_label.text()


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
    qtbot.waitUntil(started.is_set, timeout=5_000)

    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    release.set()
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=5_000)

    def broken_prepare(data: bytes, plan: EditPlan) -> PreparedEdit:
        raise SaveError("injected preview failure")

    window.service = EditorService(prepare_fn=broken_prepare)
    window._stage_stack_change(0x30000001, 4)
    with qtbot.waitSignal(window.operation_failed, timeout=5_000):
        window._start_preview()
    assert "injected preview failure" in window.error_label.text()
