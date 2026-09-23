from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from editor.capabilities import FormatCapabilities
from editor.service import EditorService
from save_format import inspect_save
from ui.main_window import LocalSnapshot, MainWindow


def test_canonical_item_detail_keeps_unconfirmed_upgrades_as_evidence(
    qtbot, synthetic_save: bytes, tmp_path
) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(
        path=tmp_path / "slot.sav",
        data=synthetic_save,
        info=inspect_save(synthetic_save, with_inventory=True),
        capabilities=FormatCapabilities(read_inventory=True),
    ))
    editor = window.editor_view
    editor.table.selectRow(0)
    qtbot.waitUntil(lambda: editor.selected_handle is not None)
    assert "read-only" in editor.detail_view.module_status.text().casefold()
