from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


from editor.capabilities import CapabilitySupport, FormatCapabilities
from editor.service import EditorService
from save_format import inspect_save
from ui.main_window import LocalSnapshot, MainWindow


def test_editor_has_status_inventory_and_detail_columns(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)

    editor = window.editor_view
    assert editor.objectName() == "editorView"
    assert editor.status_column.objectName() == "editorStatusColumn"
    assert editor.inventory_column.objectName() == "editorInventoryColumn"
    assert editor.detail_column.objectName() == "editorDetailColumn"
    assert editor.save_button.text() == "СОХРАНИТЬ 0 ИЗМЕНЕНИЙ"
    assert not editor.save_button.isEnabled()


def test_editor_capability_gates_item_controls_and_save_counter(
    qtbot, synthetic_save: bytes, tmp_path
) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "slot.sav",
            data=synthetic_save,
            info=info,
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_money": CapabilitySupport("experimental"),
                    "edit_stacks": CapabilitySupport("research"),
                },
            ),
        )
    )

    editor = window.editor_view
    assert editor.save_button.text() == "СОХРАНИТЬ 0 ИЗМЕНЕНИЙ"
    assert editor.detail_view.count_spin.isEnabled() is False
    assert editor.detail_view.remove_button.isEnabled() is False

    row = next(
        index
        for index, item in enumerate(editor.model.visible_items())
        if item.handle == 0x30000001
    )
    editor.table.selectRow(row)
    qtbot.waitUntil(lambda: editor.selected_handle == 0x30000001)
    assert editor.detail_view.status_chip.text() in {"READ-ONLY", "ЭКСПЕРИМЕНТАЛЬНО"}
