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
from ui.main_window import LocalSnapshot, MainWindow


def _item(handle: int, key: str, category: str, storage: str | None, condition: float | None, editable: bool, *, kind_code: int = 1, display_name: str | None = None, modules: tuple[str, ...] | None = None, upgrades: tuple[str, ...] | None = None) -> InventoryItem:
    return InventoryItem(
        handle=handle, x=None, y=None, width=None, height=None, cells=(), count=1,
        total_weight=None, unit_weight=None, kind_code=kind_code, category=category,
        record_offset=0, record_end_guess=64, fingerprint="f" * 64, type_key=key,
        editable_count=False, display_name=display_name or key, condition=condition,
        condition_editable=editable, storage=storage, modules=modules, upgrades=upgrades,
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


def test_equipment_model_filters_shared_product_categories() -> None:
    model = EquipmentTableModel()
    model.set_items(equipment_items(
        (
            _item(10, "ammo_9x39", "Боеприпасы", "inventory", None, False),
            _item(11, "artifact_blood", "Артефакт", "inventory", None, False),
            _item(12, "quest_key", "Квестовый предмет", "inventory", None, False),
        ),
        release_id="stalker2",
    ))
    for category, handle in (("ammo", 10), ("artifact", 11), ("quest", 12)):
        model.set_filter(category)
        assert [row.handle for row in model.visible_items()] == [handle]


def test_equipment_model_shows_s2_modules_and_device_category() -> None:
    model = EquipmentTableModel()
    model.set_items(equipment_items(
        (
            _item(10, "057601", "Устройство", "inventory", None, False, display_name="NVG_NPC_Gen3"),
            _item(11, "041a01", "Оружие", "equipped", 0.9, True, kind_code=0, display_name="GunKharod_ST", modules=("GunKharod_MagDefault", "HP_Laser_1"), upgrades=("GunKharod_Upgrade_Stock_1",)),
        ),
        release_id="stalker2",
    ))
    model.set_filter("device")
    assert [item.handle for item in model.visible_items()] == [10]
    model.set_filter("all")
    assert "GunKharod_MagDefault" in model.data(model.index(1, EquipmentTableModel.UPGRADES_COLUMN), Qt.ItemDataRole.DisplayRole)


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
