from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from test_xray_durability import _condition_fixture

from editor.capabilities import CapabilitySupport, FormatCapabilities
from editor.service import EditorService
from editor.xray_save import COP_FORMAT, inspect_xray
from ui.main_window import LocalSnapshot, MainWindow


def test_qt_placement_editor_stages_slot_without_mutating_snapshot(qtbot, tmp_path) -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=1 | (2 << 4) | (3 << 10),
    )
    info = inspect_xray(data, COP_FORMAT)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "placement.scop",
            data=data,
            info=info,
            format_id=COP_FORMAT.id,
            format_title=COP_FORMAT.title,
            release_id=COP_FORMAT.id,
            edition="original",
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_placement": CapabilitySupport("experimental")
                },
            ),
        )
    )

    view = window.editor_view
    view.table.selectRow(0)
    qtbot.waitUntil(lambda: view.selected_handle == 0x3456)

    assert view.detail_view.placement_combo.isEnabled()
    target = next(
        index
        for index in range(view.detail_view.placement_combo.count())
        if view.detail_view.placement_combo.itemData(index) == ("slot", 4)
    )
    view.detail_view.placement_combo.setCurrentIndex(target)

    assert window.staged_placements == {0x3456: ("slot", 4)}
    assert window.snapshot is not None
    assert window.snapshot.data == data
    assert window._build_edit_plan().placements == ((0x3456, "slot", 4),)
