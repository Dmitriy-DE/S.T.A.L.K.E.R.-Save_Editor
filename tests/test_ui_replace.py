from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from editor.capabilities import CapabilitySupport, FormatCapabilities
from editor.models import EditPlan, PreparedEdit
from editor.service import EditorService
from save_format import inspect_save
from ui.main_window import LocalSnapshot, MainWindow


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
        LocalSnapshot(
            path=source,
            data=synthetic_save,
            info=inspect_save(synthetic_save),
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_money": CapabilitySupport("experimental"),
                    "edit_stacks": CapabilitySupport("experimental"),
                },
            ),
        )
    )
    window._stage_stack_change(0x30000001, 3)
    window._start_preview()
    qtbot.waitUntil(lambda: window.prepared_edit is not None, timeout=5_000)

    window._start_replace(backup_dir)
    qtbot.waitSignal(window.apply_ready, timeout=5_000)
    qtbot.waitUntil(lambda: window._operation_thread is None, timeout=5_000)

    assert calls == [(source, backup_dir)]
    assert window.reference_stack.currentWidget() is window.editor_view
    assert window._reference_modal_view is window.save_result_view
    assert window.save_result_view.heading_label.text() == "СОХРАНЕНИЕ УСПЕШНО ЗАПИСАНО"
    assert "Сохранение" in {
        window.save_result_view.receipt_table.item(row, 0).text()
        for row in range(window.save_result_view.receipt_table.rowCount())
    }
