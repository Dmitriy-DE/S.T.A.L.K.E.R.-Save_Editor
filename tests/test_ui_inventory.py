from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
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
    window._render_snapshot(
        LocalSnapshot(
            path=source,
            data=synthetic_save,
            info=info,
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_money": CapabilitySupport("experimental"),
                    "edit_stacks": CapabilitySupport("experimental"),
                },
            ),
        )
    )

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
    window._render_snapshot(
        LocalSnapshot(
            path=source,
            data=synthetic_save,
            info=info,
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_money": CapabilitySupport("experimental"),
                    "edit_stacks": CapabilitySupport("experimental"),
                },
            ),
        )
    )

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
    assert window.money_card_value.text() == "100"
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


def test_inventory_model_can_present_catalog_name_without_mutating_snapshot(
    synthetic_save: bytes,
) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    model = InventoryTableModel()
    model.set_name_provider(lambda item: f"Каталог: {item.handle_hex}")
    model.set_items(info.inventory)

    assert model.data(model.index(0, model.NAME_COLUMN), Qt.ItemDataRole.DisplayRole) == (
        "Каталог: 0x30000001"
    )
    assert info.inventory[0].display_name is None


def test_inventory_layout_keeps_names_and_editor_fields_readable(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    info = inspect_save(synthetic_save, with_inventory=True)
    window._render_snapshot(
        LocalSnapshot(path=tmp_path / "fixture.sav", data=synthetic_save, info=info)
    )

    view = window.inventory_view
    header = view.table.horizontalHeader()
    assert view.scroll_area.widgetResizable() is True
    assert header.sectionResizeMode(view.model.NAME_COLUMN).name == "Interactive"
    assert view.table.minimumWidth() >= 1100
    assert view.table.minimumHeight() >= 220
    assert view.count_spin.minimumWidth() >= 180
    assert view.condition_spin.minimumWidth() >= 180


def test_unknown_condition_shows_dash_instead_of_false_zero(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    info = inspect_save(synthetic_save, with_inventory=True)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "fixture.sav",
            data=synthetic_save,
            info=info,
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_durability": CapabilitySupport("experimental")
                },
            ),
        )
    )

    view = window.inventory_view
    view.table.selectRow(0)
    qtbot.waitUntil(lambda: view.selected_handle is not None)

    assert view.condition_unknown_label.text() == "—"
    assert not view.condition_unknown_label.isHidden()
    assert view.condition_spin.isHidden()
    assert not view.condition_stage_button.isEnabled()


def test_confirmed_s2_armor_condition_is_editable(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    data = _save_with_equipped_armor(synthetic_save)
    info = inspect_save(data, with_inventory=True)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "s2-armor.sav",
            data=data,
            info=info,
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_durability": CapabilitySupport("experimental")
                },
            ),
        )
    )

    view = window.inventory_view
    row = next(
        index
        for index, item in enumerate(view.model.visible_items())
        if item.handle == EQUIPPED_HANDLE
    )
    view.table.selectRow(row)
    qtbot.waitUntil(lambda: view.selected_handle == EQUIPPED_HANDLE)

    assert view.condition_unknown_label.isHidden()
    assert not view.condition_spin.isHidden()
    assert view.condition_spin.value() == pytest.approx(75.0)
    assert view.condition_stage_button.isEnabled()
    assert "S2 STATE f32 condition anchor" in view.condition_status_label.text()


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
    assert model.data(model.index(0, model.WEIGHT_COLUMN), Qt.ItemDataRole.DisplayRole) == "—"
    assert window.format_badge.text() == f"ФОРМАТ: {COP_FORMAT.title}"
    assert window.location_card_value.text() == "—"
    assert window.inventory_view.count_spin.maximum() == 65535


def test_original_xray_inventory_stages_catalog_add_and_registry_remove(
    qtbot, tmp_path: Path
) -> None:
    data = _fixture()
    info = inspect_xray(data, COP_FORMAT)
    catalog = catalog_from_items(
        COP_FORMAT.id,
        (
            ItemDefinition(
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
            ),
        ),
    )
    source = tmp_path / "slot.scop"
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=source,
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

    assert window.inventory_view.add_button.isEnabled()
    window._stage_item_add("ammo_9x39_pab9", 12)
    handle = info.inventory[0].handle
    window._stage_item_remove(handle)

    assert window.staged_adds == {"ammo_9x39_pab9": 12}
    assert window.staged_detach == {handle: True}
    plan = window._build_edit_plan()
    assert plan.adds == (("ammo_9x39_pab9", 12, "inventory"),)
    assert plan.detach == ((handle, True),)
