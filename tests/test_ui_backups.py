from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

import editor.storage as storage
from editor.models import EditPlan, SourceRef
from editor.prepare import prepare_edit
from editor.service import EditorService
from ui.backup_controller import BackupController
from ui.history_view import HistoryView
from ui.main_window import MainWindow


def _write_journal(journal: Path, backup_path: Path, sha256: str) -> None:
    journal.write_text(
        json.dumps(
            {
                "version": 1,
                "status": "verified",
                "created_at": "2026-09-13T18:00:00+00:00",
                "source_path": "/saves/original.sav",
                "source_sha256": sha256,
                "output_path": "/saves/edited.sav",
                "output_sha256": sha256,
                "backup_path": str(backup_path),
                "operation": {"money": 900, "stack_count": 0},
            }
        ),
        encoding="utf-8",
    )


def test_history_view_renders_statuses_and_requires_preview_before_restore(
    qtbot, tmp_path: Path, synthetic_save: bytes
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    expected_sha = hashlib.sha256(synthetic_save).hexdigest()
    backup = backup_dir / "valid_ORIGINAL.sav"
    backup.write_bytes(synthetic_save)
    _write_journal(backup.with_suffix(".json"), backup, expected_sha)
    missing = backup_dir / "missing_ORIGINAL.sav"
    _write_journal(missing.with_suffix(".json"), missing, expected_sha)

    view = HistoryView(BackupController((backup_dir,)))
    qtbot.addWidget(view)
    view.refresh()

    assert view.table.rowCount() == 2
    statuses = []
    for row in range(view.table.rowCount()):
        status_chip = view.table.cellWidget(row, 4)
        assert isinstance(status_chip, QLabel)
        statuses.append(status_chip.text())
    assert "Готово к восстановлению" in statuses
    assert "Файл не найден" in statuses
    assert not view.restore_button.isEnabled()
    assert not view.restore_in_place_button.isEnabled()

    valid_row = statuses.index("Готово к восстановлению")
    view.table.selectRow(valid_row)
    view.destination_edit.setText(str(tmp_path / "restored.sav"))
    qtbot.mouseClick(view.preview_button, Qt.MouseButton.LeftButton)

    assert view.restore_button.isEnabled()
    assert not view.restore_in_place_button.isEnabled()
    assert view.detail_status.text() == "Резервная копия проверена. Её можно восстановить."
    assert "SHA" not in view.detail_status.text()


def test_main_window_runs_restore_off_ui_thread_and_reports_receipt(
    qtbot, tmp_path: Path, synthetic_save: bytes
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    expected_sha = hashlib.sha256(synthetic_save).hexdigest()
    backup = backup_dir / "valid_ORIGINAL.sav"
    backup.write_bytes(synthetic_save)
    _write_journal(backup.with_suffix(".json"), backup, expected_sha)

    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window.backup_controller.backup_dirs = (backup_dir,)
    window.backup_controller.refresh()
    record = window.backup_controller.records[0]
    destination = tmp_path / "restored.sav"

    with qtbot.waitSignal(window.restore_ready, timeout=5_000):
        window._start_restore(record, destination)

    qtbot.waitUntil(lambda: window._operation_thread is None, timeout=5_000)
    assert destination.read_bytes() == synthetic_save
    assert window.history_reference_view.detail_status.text() == (
        "Резервная копия восстановлена и проверена."
    )


def test_main_window_can_restore_verified_backup_to_original_slot(
    qtbot, tmp_path: Path, synthetic_save: bytes
) -> None:
    source = tmp_path / "slot.sav"
    source.write_bytes(synthetic_save)
    plan = EditPlan(
        source=SourceRef(
            kind="local",
            locator=str(source),
            sha256=hashlib.sha256(synthetic_save).hexdigest(),
        ),
        money=900,
    )
    prepared = prepare_edit(synthetic_save, plan)
    backup_dir = tmp_path / "backups"
    replaced = storage.replace_local(source, prepared, backup_dir)
    record = storage.inspect_backup(replaced.backup_path.with_suffix(".json"))

    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window.backup_controller.backup_dirs = (backup_dir,)
    window.backup_controller.refresh()
    window.history_reference_view.table.selectRow(0)
    qtbot.mouseClick(window.history_reference_view.preview_button, Qt.MouseButton.LeftButton)
    assert window.history_reference_view.restore_in_place_button.isEnabled()

    with qtbot.waitSignal(window.restore_ready, timeout=5_000):
        window._start_restore_in_place(record)

    qtbot.waitUntil(lambda: window._operation_thread is None, timeout=5_000)
    assert source.read_bytes() == synthetic_save
    assert window.history_reference_view.detail_status.text() == (
        "Исходное сохранение восстановлено и проверено."
    )
