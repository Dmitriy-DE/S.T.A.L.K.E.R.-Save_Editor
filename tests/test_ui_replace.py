from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt

from editor.models import EditPlan, PreparedEdit
from editor.service import EditorService
from save_format import inspect_save
from ui.changes_view import ChangesView
from ui.main_window import LocalSnapshot, MainWindow


def test_changes_view_exposes_explicit_in_place_replace_action(qtbot) -> None:
    view = ChangesView()
    qtbot.addWidget(view)

    assert not view.replace_button.isEnabled()
    view.set_actions_enabled(preview=True, apply=True, replace=True, busy=False)
    assert view.replace_button.isEnabled()

    with qtbot.waitSignal(view.replace_requested, timeout=1_000):
        qtbot.mouseClick(view.replace_button, Qt.MouseButton.LeftButton)

    view.set_actions_enabled(preview=True, apply=True, replace=False, busy=False)
    assert not view.replace_button.isEnabled()


def test_main_window_replaces_the_selected_local_slot_after_preview(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "slot.sav"
    source.write_bytes(synthetic_save)
    backup_dir = tmp_path / "backups"
    calls: list[tuple[Path, Path]] = []

    def prepare(data: bytes, plan: EditPlan) -> PreparedEdit:
        return PreparedEdit(
            plan=plan,
            data=data,
            output_sha256=hashlib.sha256(data).hexdigest(),
        )

    def replace(source_path: Path, prepared: PreparedEdit, backup: Path):
        calls.append((source_path, backup))
        assert source_path == source
        assert prepared.plan.source.locator == str(source)
        return type(
            "Receipt",
            (),
            {
                "output_path": source,
                "backup_path": backup / "slot_ORIGINAL.sav",
                "output_sha256": prepared.output_sha256,
            },
        )()

    window = MainWindow(
        EditorService(prepare_fn=prepare, replace_fn=replace),
    )
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(path=source, data=synthetic_save, info=inspect_save(synthetic_save))
    )
    window._stage_stack_change(0x30000001, 3)
    window._start_preview()
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=5_000)

    window._start_replace(backup_dir)
    qtbot.waitSignal(window.apply_ready, timeout=5_000)
    qtbot.waitUntil(lambda: window._operation_thread is None, timeout=5_000)

    assert calls == [(source, backup_dir)]
    assert "Исходный слот заменён" in window.changes_view.preview_status_label.text()
