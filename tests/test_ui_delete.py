from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from test_xray_durability import _condition_fixture

from editor.capabilities import FormatCapabilities
from editor.service import EditorService
from editor.xray_save import COP_FORMAT, inspect_xray
from ui.main_window import LocalSnapshot, MainWindow


def test_qt_delete_button_shows_equipped_blocker_and_does_not_stage(
    qtbot, tmp_path
) -> None:
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
            path=tmp_path / "equipped.scop",
            data=data,
            info=info,
            format_id=COP_FORMAT.id,
            format_title=COP_FORMAT.title,
            release_id=COP_FORMAT.id,
            edition="original",
            capabilities=FormatCapabilities(
                read_inventory=True,
                edit_stacks=True,
                remove_items=True,
            ),
        )
    )

    view = window.inventory_view
    view.table.selectRow(0)
    qtbot.waitUntil(lambda: view.selected_handle == info.inventory[0].handle)

    assert not view.remove_item_button.isEnabled()
    assert "equipped" in view.editability_label.text()
    window._stage_item_remove(info.inventory[0].handle)
    assert window.staged_detach == {}
