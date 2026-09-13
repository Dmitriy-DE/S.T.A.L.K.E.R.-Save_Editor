from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt

from editor.service import EditorService
from ui.main_window import MainWindow
from ui.backups_view import BackupView


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


def test_backup_view_renders_statuses_and_requires_preview_before_restore(
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

    view = BackupView((backup_dir,))
    qtbot.addWidget(view)
    view.refresh()

    assert view.table.rowCount() == 2
    statuses = [
        view.table.item(row, view.STATUS_COLUMN).text()
        for row in range(view.table.rowCount())
    ]
    assert "Проверено" in statuses
    assert "Отсутствует" in statuses
    assert not view.restore_button.isEnabled()

    valid_row = statuses.index("Проверено")
    view.table.selectRow(valid_row)
    view.destination_edit.setText(str(tmp_path / "restored.sav"))
    qtbot.mouseClick(view.preview_button, Qt.MouseButton.LeftButton)

    assert view.restore_button.isEnabled()
    assert "SHA256" in view.preview_label.text()


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
    window.backups_view.backup_dirs = (backup_dir,)
    window.backups_view.refresh()
    record = window.backups_view.records[0]
    destination = tmp_path / "restored.sav"

    with qtbot.waitSignal(window.restore_ready, timeout=5_000):
        window._start_restore(record, destination)

    qtbot.waitUntil(lambda: window._operation_thread is None, timeout=5_000)
    assert destination.read_bytes() == synthetic_save
    assert "Копия восстановлена" in window.backups_view.preview_label.text()
