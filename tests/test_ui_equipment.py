from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from test_xray_durability import _condition_fixture

from editor.equipment import equipment_items
from editor.formats import by_id
from editor.service import EditorService
from editor.xray_save import COP_FORMAT, inspect_xray
from save_format import InventoryItem
from ui.equipment_model import EquipmentTableModel
from ui.equipment_view import EquipmentView
from ui.main_window import LocalSnapshot, MainWindow


def _item(handle: int, key: str, category: str, storage: str | None, condition: float | None, editable: bool) -> InventoryItem:
    return InventoryItem(
        handle=handle,
        x=None,
        y=None,
        width=None,
        height=None,
        cells=(),
        count=1,
        total_weight=None,
        unit_weight=None,
        kind_code=1,
        category=category,
        record_offset=0,
        record_end_guess=64,
        fingerprint="f" * 64,
        type_key=key,
        editable_count=False,
        display_name=key,
        condition=condition,
        condition_editable=editable,
        storage=storage,  # type: ignore[arg-type]
    )


def _rows():
    return equipment_items(
        (
            _item(1, "wpn_test", "Оружие", "equipped", 0.5, True),
            _item(2, "outfit_test", "Броня/экипировка", "inventory", 0.75, True),
            _item(3, "helm_test", "Броня/экипировка", "equipped", 1.0, True),
        ),
        release_id="stalker-cop",
    )


def test_equipment_model_filters_by_product_category_and_location() -> None:
    model = EquipmentTableModel()
    model.set_items(_rows())

    assert [row.handle for row in model.visible_items()] == [1, 2, 3]
    model.set_filter("weapon")
    assert [row.handle for row in model.visible_items()] == [1]
    model.set_filter("equipped")
    assert [row.handle for row in model.visible_items()] == [1, 3]
    model.set_filter("all")
    model.set_search("helm_test")
    assert [row.handle for row in model.visible_items()] == [3]
    model.set_search("")
    model.sort(EquipmentTableModel.NAME_COLUMN, Qt.SortOrder.DescendingOrder)
    assert [row.handle for row in model.visible_items()] == [1, 2, 3]


def test_equipment_view_emits_individual_and_bulk_repair_requests(qtbot) -> None:
    view = EquipmentView()
    qtbot.addWidget(view)
    view.set_items(_rows())
    view.table.selectRow(0)
    qtbot.waitUntil(lambda: view.selected_handle == 1)
    view.percent_spin.setValue(100)

    with qtbot.waitSignal(view.repair_requested, timeout=1000) as individual:
        qtbot.mouseClick(view.repair_button, Qt.MouseButton.LeftButton)
    assert individual.args == [1, 100.0]

    with qtbot.waitSignal(view.bulk_repair_requested, timeout=1000) as bulk:
        qtbot.mouseClick(view.bulk_damaged_button, Qt.MouseButton.LeftButton)
    assert bulk.args == ["damaged", 100.0]


def test_equipment_view_disables_read_only_repair_with_reason(qtbot) -> None:
    view = EquipmentView()
    qtbot.addWidget(view)
    view.set_items(
        equipment_items(
            (_item(8, "weapon_s2", "Оружие", "inventory", 0.5, True),),
            release_id="stalker2",
        )
    )
    view.table.selectRow(0)
    qtbot.waitUntil(lambda: view.selected_handle == 8)

    assert not view.repair_button.isEnabled()
    assert "research" in view.status_label.text()


def test_equipment_view_hides_helmet_controls_for_releases_without_them(qtbot) -> None:
    view = EquipmentView()
    qtbot.addWidget(view)

    helmet_index = view.filter_combo.findData("helmet")
    view.set_release("stalker-soc")
    assert view.filter_combo.view().isRowHidden(helmet_index)
    assert view.bulk_helmet_button.isHidden()

    view.set_release("stalker-cop")
    assert not view.filter_combo.view().isRowHidden(helmet_index)
    assert not view.bulk_helmet_button.isHidden()


def test_main_window_stages_equipment_bulk_repair_through_existing_plan(qtbot, tmp_path) -> None:
    data = _condition_fixture(version=128, outer=6, name="wpn_test")
    info = inspect_xray(data, COP_FORMAT)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "equipment.scop",
            data=data,
            info=info,
            format_id=COP_FORMAT.id,
            format_title=COP_FORMAT.title,
            release_id=COP_FORMAT.id,
            edition="original",
            capabilities=by_id("stalker-cop").capabilities,
        )
    )

    assert window.equipment_view.model.visible_items()[0].category == "weapon"
    window.equipment_view.percent_spin.setValue(100)
    qtbot.mouseClick(window.equipment_view.bulk_damaged_button, Qt.MouseButton.LeftButton)

    assert window.staged_durability == {0x3456: 1.0}
    assert window._build_edit_plan().durability == ((0x3456, 1.0),)
    assert window.snapshot is not None and window.snapshot.data == data
