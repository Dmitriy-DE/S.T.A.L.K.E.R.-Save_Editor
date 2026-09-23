from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from test_s2_equipment_inventory import EQUIPPED_HANDLE, _save_with_equipped_armor
from test_xray_save import _fixture

from editor.capabilities import CapabilitySupport, FormatCapabilities
from editor.catalog import ItemDefinition, catalog_from_items
from editor.service import EditorService
from editor.xray_save import COP_FORMAT, inspect_xray
from save_format import inspect_save
from ui.inventory_model import InventoryTableModel
from ui.main_window import LocalSnapshot, MainWindow


def test_inventory_model_filters_and_sort_keep_handle_identity(synthetic_save: bytes) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    model = InventoryTableModel()
    model.set_items(info.inventory)
    assert [item.handle for item in model.visible_items()] == [0x30000001, 0x30000002]
    model.sort(0, Qt.SortOrder.DescendingOrder)
    assert [item.handle for item in model.visible_items()] == [0x30000002, 0x30000001]
    model.set_search("040506")
    assert [item.handle for item in model.visible_items()] == [0x30000002]
    model.set_search("")
    model.set_category("Расходник")
    assert [item.handle for item in model.visible_items()] == [0x30000001]
    model.set_category("Все")
    model.set_changed_handles({0x30000002})
    model.set_changed_only(True)
    assert [item.handle for item in model.visible_items()] == [0x30000002]


def _window(qtbot, synthetic_save: bytes, tmp_path: Path, *, capabilities: FormatCapabilities | None = None) -> MainWindow:
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "fixture.sav",
            data=synthetic_save,
            info=info,
            capabilities=capabilities or FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_money": CapabilitySupport("experimental"),
                    "edit_stacks": CapabilitySupport("experimental"),
                },
            ),
        )
    )
    return window


def test_editor_table_stages_by_handle_after_filter_and_sort(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = _window(qtbot, synthetic_save, tmp_path)
    editor = window.editor_view
    stack_handle = 0x30000001
    row = next(index for index, item in enumerate(editor.model.visible_items()) if item.handle == stack_handle)
    editor.table.selectRow(row)
    qtbot.waitUntil(lambda: editor.selected_handle == stack_handle)
    assert editor.detail_view.count_spin.isEnabled()
    editor.detail_view.count_spin.setValue(3)
    editor.detail_view.count_spin.setValue(3)
    assert window.staged_counts == {stack_handle: 3}
    assert window.snapshot is not None and window.snapshot.data == synthetic_save
    editor.search_edit.setText("30000001")
    assert [item.handle for item in editor.model.visible_items()] == [stack_handle]
    editor.model.sort(0, Qt.SortOrder.DescendingOrder)
    assert editor.model.visible_items()[0].handle == stack_handle
    assert window.staged_counts == {stack_handle: 3}


def test_count_one_is_read_only_and_invalid_count_never_stages(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = _window(qtbot, synthetic_save, tmp_path)
    editor = window.editor_view
    single_handle = 0x30000002
    editor.table.selectRow(next(index for index, item in enumerate(editor.model.visible_items()) if item.handle == single_handle))
    qtbot.waitUntil(lambda: editor.selected_handle == single_handle)
    assert not editor.detail_view.count_spin.isEnabled()
    window._stage_stack_change(single_handle, 99)
    assert window.staged_counts == {}
    window._stage_stack_change(0x30000001, 0)
    assert window.staged_counts == {}
    assert "1..1000000" in editor.detail_view.module_status.text()


def test_money_form_stages_without_mutating_snapshot(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = _window(qtbot, synthetic_save, tmp_path)
    editor = window.editor_view
    assert editor.money_spin.isEnabled()
    assert editor.money_spin.value() == 100
    editor.money_spin.setValue(900)
    # The money field edits the shared draft directly; there is no per-field apply action.
    assert window.staged_money == 900
    assert window.snapshot is not None and window.snapshot.data == synthetic_save
    editor.money_clear_button.click()
    assert window.staged_money is None


def test_read_only_capabilities_disable_money_and_stack_staging(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = _window(qtbot, synthetic_save, tmp_path, capabilities=FormatCapabilities(read_inventory=True))
    editor = window.editor_view
    assert not editor.money_spin.isEnabled()
    assert not editor.money_spin.isEnabled()
    window._stage_stack_change(0x30000001, 3)
    assert window.staged_counts == {}


def test_unknown_display_name_is_honest_and_handle_is_visible(synthetic_save: bytes) -> None:
    model = InventoryTableModel()
    model.set_items(inspect_save(synthetic_save, with_inventory=True).inventory)
    assert model.data(model.index(0, model.NAME_COLUMN), Qt.ItemDataRole.DisplayRole) == "Неизвестный объект"
    assert model.data(model.index(0, model.HANDLE_COLUMN), Qt.ItemDataRole.DisplayRole).startswith("0x300000")


def test_editor_uses_canonical_three_column_geometry(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = _window(qtbot, synthetic_save, tmp_path)
    editor = window.editor_view
    assert editor.table.horizontalHeader().sectionResizeMode(editor.model.NAME_COLUMN).name == "Interactive"
    assert editor.detail_column.objectName() == "editorDetailColumn"
    assert editor.money_spin.minimum() == 0


def test_confirmed_s2_armor_condition_is_editable(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    data = _save_with_equipped_armor(synthetic_save)
    info = inspect_save(data, with_inventory=True)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "s2-armor.sav",
            data=data,
            info=info,
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={"edit_durability": CapabilitySupport("experimental")},
            ),
        )
    )
    editor = window.editor_view
    row = next(index for index, item in enumerate(editor.model.visible_items()) if item.handle == EQUIPPED_HANDLE)
    editor.table.selectRow(row)
    qtbot.waitUntil(lambda: editor.selected_handle == EQUIPPED_HANDLE)
    assert editor.detail_view.condition_spin.isEnabled()
    assert editor.detail_view.condition_spin.value() == pytest.approx(75.0)


def test_original_xray_inventory_keeps_serialized_name_and_unknown_weight(qtbot, tmp_path: Path) -> None:
    data = _fixture()
    info = inspect_xray(data, COP_FORMAT)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(path=tmp_path / "slot.scop", data=data, info=info, format_id=COP_FORMAT.id, format_title=COP_FORMAT.title))
    model = window.editor_view.model
    item = info.inventory[0]
    assert model.data(model.index(0, model.NAME_COLUMN), Qt.ItemDataRole.DisplayRole) == item.display_name
    assert model.data(model.index(0, model.WEIGHT_COLUMN), Qt.ItemDataRole.DisplayRole) == "—"
    assert COP_FORMAT.title in window.editor_view.breadcrumb.text()
    assert window.editor_view.detail_view.count_spin.maximum() == 65535


def test_original_xray_inventory_stages_catalog_add_and_registry_remove(qtbot, tmp_path: Path) -> None:
    data = _fixture()
    info = inspect_xray(data, COP_FORMAT)
    catalog = catalog_from_items(
        COP_FORMAT.id,
        (ItemDefinition(
            key="ammo_9x39_pab9",
            display_name="9x39",
            category="ammo",
            unit_weight=0.5,
            width=1,
            height=1,
            max_stack=30,
            slots=(),
            prototype=None,
            source="test-catalog",
            class_name="AMMO",
            serialization_family="ammo",
        ),),
    )
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "slot.scop",
            data=data,
            info=info,
            format_id=COP_FORMAT.id,
            format_title=COP_FORMAT.title,
            release_id=COP_FORMAT.id,
            edition="original",
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_money": CapabilitySupport("verified"),
                    "edit_stacks": CapabilitySupport("verified"),
                    "add_items": CapabilitySupport("verified"),
                    "remove_items": CapabilitySupport("verified"),
                },
                catalog=True,
            ),
            catalog=catalog,
        )
    )
    window._stage_item_add("ammo_9x39_pab9", 12)
    handle = info.inventory[0].handle
    window._stage_item_remove(handle)
    assert window.staged_adds == {"ammo_9x39_pab9": 12}
    assert window.staged_detach == {handle: True}
    plan = window._build_edit_plan()
    assert plan.adds == (("ammo_9x39_pab9", 12, "inventory"),)
    assert plan.detach == ((handle, True),)
