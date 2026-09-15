from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from test_xray_save import _fixture

from editor.capabilities import FormatCapabilities
from editor.service import EditorService
from editor.xray_save import COP_FORMAT, inspect_xray
from save_format import inspect_save
from ui.inventory_model import InventoryTableModel
from ui.main_window import LocalSnapshot, MainWindow


def test_inventory_model_filters_and_sort_keep_handle_identity(synthetic_save: bytes) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    model = InventoryTableModel()
    model.set_items(info.inventory)

    assert [item.handle for item in model.visible_items()] == [
        0x30000001,
        0x30000002,
    ]

    model.sort(0, Qt.SortOrder.DescendingOrder)
    assert [item.handle for item in model.visible_items()] == [
        0x30000002,
        0x30000001,
    ]

    model.set_search("040506")
    assert [item.handle for item in model.visible_items()] == [0x30000002]

    model.set_search("")
    model.set_category("Расходник")
    assert [item.handle for item in model.visible_items()] == [0x30000001]

    model.set_category("Все")
    model.set_changed_handles({0x30000002})
    model.set_changed_only(True)
    assert [item.handle for item in model.visible_items()] == [0x30000002]


def test_inventory_table_stages_by_handle_after_filter_and_sort(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "fixture.sav"
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(path=source, data=synthetic_save, info=info))

    view = window.inventory_view
    stack_handle = 0x30000001
    row = next(
        index
        for index, item in enumerate(view.model.visible_items())
        if item.handle == stack_handle
    )
    view.table.selectRow(row)
    qtbot.waitUntil(lambda: view.selected_handle == stack_handle)
    assert view.count_spin.isEnabled()
    assert view.stage_button.isEnabled()

    view.count_spin.setValue(3)
    qtbot.mouseClick(view.stage_button, Qt.MouseButton.LeftButton)
    assert window.staged_counts == {stack_handle: 3}
    assert window.snapshot is not None
    assert window.snapshot.data == synthetic_save

    view.search_edit.setText("30000001")
    QApplication.processEvents()
    assert [item.handle for item in view.model.visible_items()] == [stack_handle]
    view.model.sort(0, Qt.SortOrder.DescendingOrder)
    assert view.model.visible_items()[0].handle == stack_handle
    assert window.staged_counts == {stack_handle: 3}
    assert "3" in view.model.data(view.model.index(0, view.model.COUNT_COLUMN))

    qtbot.mouseClick(view.clear_selected_button, Qt.MouseButton.LeftButton)
    assert window.staged_counts == {}


def test_count_one_is_read_only_and_invalid_count_never_stages(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "fixture.sav"
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(path=source, data=synthetic_save, info=info))

    view = window.inventory_view
    single_handle = 0x30000002
    row = next(
        index
        for index, item in enumerate(view.model.visible_items())
        if item.handle == single_handle
    )
    view.table.selectRow(row)
    qtbot.waitUntil(lambda: view.selected_handle == single_handle)
    assert not view.count_spin.isEnabled()
    assert not view.stage_button.isEnabled()
    assert "count=1" in view.editability_label.text()

    window._stage_stack_change(single_handle, 99)
    assert window.staged_counts == {}

    stack_handle = 0x30000001
    window._stage_stack_change(stack_handle, 0)
    assert window.staged_counts == {}
    assert "1..1000000" in view.editability_label.text()


def test_money_form_stages_without_mutating_snapshot(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "fixture.sav"
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(path=source, data=synthetic_save, info=info))

    assert window.money_spin.isEnabled()
    assert window.money_spin.value() == 100
    window.money_spin.setValue(900)
    qtbot.mouseClick(window.money_stage_button, Qt.MouseButton.LeftButton)
    assert window.staged_money == 900
    assert window.snapshot is not None
    assert window.snapshot.data == synthetic_save
    assert "100" in window.money_status_label.text()
    assert "900" in window.money_status_label.text()

    qtbot.mouseClick(window.money_clear_button, Qt.MouseButton.LeftButton)
    assert window.staged_money is None


def test_read_only_capabilities_disable_money_and_stack_staging(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "readonly.sav"
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=source,
            data=synthetic_save,
            info=info,
            capabilities=FormatCapabilities(read_inventory=True),
        )
    )

    assert not window.money_spin.isEnabled()
    assert not window.money_stage_button.isEnabled()
    window._stage_stack_change(0x30000001, 3)
    assert window.staged_counts == {}


def test_unknown_display_name_is_honest_and_handle_is_visible(
    synthetic_save: bytes,
) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    model = InventoryTableModel()
    model.set_items(info.inventory)

    name = model.data(model.index(0, model.NAME_COLUMN), Qt.ItemDataRole.DisplayRole)
    handle = model.data(model.index(0, model.HANDLE_COLUMN), Qt.ItemDataRole.DisplayRole)
    assert name == "Неизвестный объект"
    assert handle.startswith("0x300000")


def test_original_xray_inventory_keeps_serialized_name_and_unknown_weight(
    qtbot, tmp_path: Path
) -> None:
    data = _fixture()
    source = tmp_path / "slot.scop"
    info = inspect_xray(data, COP_FORMAT)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    window._render_snapshot(
        LocalSnapshot(
            path=source,
            data=data,
            info=info,
            format_id=COP_FORMAT.id,
            format_title=COP_FORMAT.title,
        )
    )

    item = info.inventory[0]
    model = window.inventory_view.model
    assert model.data(model.index(0, model.NAME_COLUMN), Qt.ItemDataRole.DisplayRole) == item.display_name
    assert model.data(model.index(0, model.WEIGHT_COLUMN), Qt.ItemDataRole.DisplayRole) == "неизвестно"
    assert window.format_badge.text() == f"ФОРМАТ: {COP_FORMAT.title}"
    assert window.location_card_value.text() == "неизвестно"
    assert window.inventory_view.count_spin.maximum() == 65535
