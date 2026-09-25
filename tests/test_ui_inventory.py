from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QToolButton
from test_s2_equipment_inventory import EQUIPPED_HANDLE, _save_with_equipped_armor
from test_xray_save import _fixture

import ui.editor_view as editor_view_module
from editor.capabilities import CapabilitySupport, FormatCapabilities
from editor.catalog import ItemDefinition, catalog_from_items
from editor.catalog_bundle import load_catalog_file
from editor.service import EditorService
from editor.xray_save import COP_FORMAT, inspect_xray
from save_format import inspect_save
from tools.render_ui_review import _review_inventory, _snapshot
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


def test_canonical_save_and_inventory_tables_use_horizontal_rules_not_grid_cells(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    window = _window(qtbot, synthetic_save, tmp_path)
    tables = (
        window.library_view.save_table,
        window.library_view.activity_table,
        window.editor_view.table,
        window.cloud_reference_view.save_table,
        window.history_reference_view.table,
        window.character_view.faction_table,
        window.save_review_view.changes_table,
        window.save_result_view.receipt_table,
    )

    assert all(not table.showGrid() for table in tables)


def test_single_round_count_is_editable_and_invalid_count_never_stages(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = _window(qtbot, synthetic_save, tmp_path)
    editor = window.editor_view
    single_handle = 0x30000002  # one round (kind 5): same stack record as a pile
    editor.table.selectRow(next(index for index, item in enumerate(editor.model.visible_items()) if item.handle == single_handle))
    qtbot.waitUntil(lambda: editor.selected_handle == single_handle)
    assert editor.detail_view.count_spin.isEnabled()
    window._stage_stack_change(single_handle, 99)
    assert window.staged_counts == {single_handle: 99}
    window.staged_counts.clear()
    window._stage_stack_change(0x30000001, 0)
    assert window.staged_counts == {}
    assert "1..1000000" in editor.detail_view.module_status.text()


def test_money_form_stages_without_mutating_snapshot(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    window = _window(qtbot, synthetic_save, tmp_path)
    editor = window.editor_view
    assert editor.money_icon.accessibleName() == "Деньги"
    assert not any(
        label.text() == "ДЕНЬГИ" and label.isVisible()
        for label in editor.status_column.findChildren(QLabel)
    )
    assert editor.money_spin.locale().name() == "ru_RU"
    assert not editor.money_icon.isHidden()
    assert editor.weight_icon.accessibleName() == "Вес"
    assert editor.weight_label.text().endswith("кг")
    assert editor.money_spin.isEnabled()
    assert editor.money_spin.value() == 100
    selected = editor.model.visible_items()[1].handle
    editor.select_handle(selected)
    qtbot.waitUntil(lambda: editor.selected_handle == selected)
    editor.money_spin.setValue(9_999_999)
    assert "," not in editor.money_spin.text()
    editor.money_spin.setValue(900)
    # The money field edits the shared draft directly; there is no per-field apply action.
    assert window.staged_money == 900
    assert window.snapshot is not None and window.snapshot.data == synthetic_save
    assert editor.selected_handle == selected
    assert [index.row() for index in editor.table.selectionModel().selectedRows()] == [1]
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


def test_equipment_cards_match_slot_hierarchy_and_options_select_the_item(
    qtbot, tmp_path: Path
) -> None:
    catalog_bundle = load_catalog_file(
        Path(__file__).resolve().parents[1] / "web" / "catalogs.json"
    )["stalker-cop"]
    data = _fixture()
    info = _review_inventory(inspect_xray(data, COP_FORMAT), catalog_bundle)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "equipment.scop",
            data=data,
            info=info,
            format_id=COP_FORMAT.id,
            format_title=COP_FORMAT.title,
            release_id=COP_FORMAT.id,
            capabilities=FormatCapabilities(read_inventory=True),
            catalog=catalog_bundle.items,
        )
    )
    editor = window.editor_view
    cards = editor.status_column.findChildren(QToolButton, "equipmentSlot")
    captions = [label.text() for label in editor.status_column.findChildren(QLabel, "equipmentSlotCaption")]

    # Cards come from the real loadout categories; a quest container is not
    # equipment and the first weapon is not claimed to be the "primary" one.
    assert len(cards) == 5
    assert captions == ["ОРУЖИЕ", "ОРУЖИЕ", "БРОНЯ", "ШЛЕМ", "ДЕТЕКТОР"]
    weapon_handles = {row.handle for row in editor.equipment_rows if row.category == "weapon"}
    cards[0].click()
    assert editor.selected_handle in weapon_handles


def test_editor_visual_fixture_keeps_canonical_inventory_order_and_counts() -> None:
    catalog_bundle = load_catalog_file(
        Path(__file__).resolve().parents[1] / "web" / "catalogs.json"
    )["stalker-cop"]
    info = _review_inventory(inspect_xray(_fixture(), COP_FORMAT), catalog_bundle)
    first_rows = tuple(item.type_key for item in info.inventory[:14])

    assert first_rows == (
        "mp_wpn_ak74",
        "mp_wpn_toz34",
        "cs_heavy_outfit",
        "helm_respirator",
        "detector_advanced",
        "ammo_9x39_pab9",
        "ammo_5.45x39_fmj",
        "medkit",
        "bandage",
        "bread",
        "energy_drink",
        "af_gravi",
        "af_cristall",
        "af_electra_sparkler",
    )
    counts = {item.type_key: item.count for item in info.inventory}
    assert {key: counts[key] for key in (
        "ammo_9x39_pab9",
        "ammo_5.45x39_fmj",
        "medkit",
        "bandage",
        "bread",
        "energy_drink",
    )} == {
        "ammo_9x39_pab9": 120,
        "ammo_5.45x39_fmj": 300,
        "medkit": 5,
        "bandage": 12,
        "bread": 7,
        "energy_drink": 4,
    }


def test_s2_review_equipment_caption_uses_official_item_key_with_cop_catalog(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    catalog_bundle = load_catalog_file(
        Path(__file__).resolve().parents[1] / "web" / "catalogs.json"
    )["stalker-cop"]
    xray_info = _review_inventory(inspect_xray(_fixture(), COP_FORMAT), catalog_bundle)
    local = _snapshot(synthetic_save, tmp_path)
    snapshot = replace(
        local,
        info=replace(local.info, inventory=xray_info.inventory),
        catalog=catalog_bundle.items,
        game_catalog=catalog_bundle.game_catalog,
    )
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(10)
    window._render_snapshot(snapshot)

    captions = [
        label.text()
        for label in window.editor_view.status_column.findChildren(
            QLabel, "equipmentSlotCaption"
        )
        if label.isVisible()
    ]
    # Labels come from the item category, never from a hard-coded fixture key.
    assert captions[:2] == ["ОРУЖИЕ", "ОРУЖИЕ"]
    assert "КОНТЕЙНЕР" not in captions
    assert "ОСНОВНОЕ ОРУЖИЕ" not in captions


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
    condition_index = editor.model.index(row, InventoryTableModel.CONDITION_COLUMN)
    condition_delegate = getattr(editor_view_module, "ConditionBarDelegate", None)
    assert condition_delegate is not None
    assert isinstance(
        editor.table.itemDelegateForColumn(InventoryTableModel.CONDITION_COLUMN),
        condition_delegate,
    )
    assert editor.model.data(condition_index, Qt.ItemDataRole.DisplayRole) == ""
    assert editor.model.data(condition_index, Qt.ItemDataRole.AccessibleTextRole) == "75.0%"
    assert editor.model.data(condition_index, Qt.ItemDataRole.UserRole) == pytest.approx(0.75)
    window._stage_item_durability(EQUIPPED_HANDLE, 0.92)
    assert editor.model.data(condition_index, Qt.ItemDataRole.UserRole) == pytest.approx(0.92)
    assert editor.model.data(condition_index, Qt.ItemDataRole.AccessibleTextRole) == "75.0% → 92.0%"


def test_editor_status_facts_use_single_line_label_value_rows(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(path=tmp_path / "facts.sav", data=synthetic_save, info=info)
    )

    editor = window.editor_view
    for value_label in (
        editor.source_label,
        editor.integrity_label,
        editor.capability_label,
    ):
        assert "\n" not in value_label.text()
        assert value_label.parentWidget().objectName() == "editorInfoRow"
        assert value_label.height() == 30


def test_original_xray_inventory_uses_official_name_and_unknown_weight(qtbot, tmp_path: Path) -> None:
    data = _fixture()
    info = inspect_xray(data, COP_FORMAT)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(path=tmp_path / "slot.scop", data=data, info=info, format_id=COP_FORMAT.id, format_title=COP_FORMAT.title))
    model = window.editor_view.model
    # No catalogue next to the save: the name still comes from the official
    # Enhanced Edition snapshot (in Call of Pripyat this section is SP-5).
    assert info.inventory[0].display_name == "ammo_9x39_pab9"
    assert model.data(model.index(0, model.NAME_COLUMN), Qt.ItemDataRole.DisplayRole) == "9х39 мм СП-5"
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
