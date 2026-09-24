from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from test_xray_durability import _condition_fixture

from editor.formats import by_id
from editor.service import EditorService
from editor.xray_save import COP_FORMAT, inspect_xray
from ui.main_window import LocalSnapshot, MainWindow


def test_canonical_editor_stages_equipment_repair_through_same_draft(qtbot, tmp_path) -> None:
    data = _condition_fixture(version=128, outer=6, name="wpn_test")
    info = inspect_xray(data, COP_FORMAT)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(
        path=tmp_path / "equipment.scop",
        data=data,
        info=info,
        format_id=COP_FORMAT.id,
        format_title=COP_FORMAT.title,
        release_id=COP_FORMAT.id,
        edition="original",
        capabilities=by_id("stalker-cop").capabilities,
    ))

    assert window.editor_view.equipment_rows
    window._stage_equipment_bulk_repair("damaged", 100.0)
    assert window.staged_durability == {0x3456: 1.0}
    assert window._build_edit_plan().durability == ((0x3456, 1.0),)
    assert window.snapshot is not None and window.snapshot.data == data
