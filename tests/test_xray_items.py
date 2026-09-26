from __future__ import annotations

from pathlib import Path

import pytest
from test_xray_save import _ammo_catalog, _fixture, _fixture_with_base_item

from editor.models import EditPlan, SourceRef
from editor.xray_save import COP_FORMAT, XRaySaveError, parse_xray, prepare_xray


def _source(data: bytes) -> SourceRef:
    import hashlib

    return SourceRef(
        kind="local",
        locator="items-fixture.scop",
        sha256=hashlib.sha256(data).hexdigest(),
    )


def test_catalog_item_add_and_delete_are_round_trip_verified() -> None:
    data = _fixture()
    before = parse_xray(data, COP_FORMAT)
    added = prepare_xray(
        data,
        EditPlan(source=_source(data), adds=(("ammo_new", 2, "inventory"),)),
        COP_FORMAT,
        catalog=_ammo_catalog(),
    )
    after_add = parse_xray(added.data, COP_FORMAT)
    assert len(after_add.inventory) == len(before.inventory) + 1
    assert added.data != data

    removed = prepare_xray(
        added.data,
        EditPlan(source=_source(added.data), detach=((0x1234, True),)),
        COP_FORMAT,
    )
    with pytest.raises(XRaySaveError, match="не найден"):
        parse_xray(removed.data, COP_FORMAT).object_by_id(0x1234)


def test_non_stack_item_remains_read_only_for_count_edits() -> None:
    data = _fixture_with_base_item()
    item = parse_xray(data, COP_FORMAT).inventory[0]

    assert item.count is None
    assert item.editable_count is False
    with pytest.raises(XRaySaveError, match="count|stack"):
        prepare_xray(
            data,
            EditPlan(source=_source(data), stacks=((item.handle, 2),)),
            COP_FORMAT,
        )


def test_item_change_surfaces_keep_unproven_mutations_read_only() -> None:
    detail = Path(__file__).parents[1] / "ui" / "item_detail_view.py"
    page = Path(__file__).parents[1] / "web" / "index.html"
    browser = Path(__file__).parents[1] / "web" / "app.js"

    assert "S2 add/remove surface is omitted" in detail.read_text(encoding="utf-8")
    assert "Исходный файл не изменяется" in page.read_text(encoding="utf-8")
    assert "item.remove_editable && caps.remove_items" in browser.read_text(encoding="utf-8")


def test_added_clone_never_keeps_the_templates_worn_slot() -> None:
    """Clear Sky: a cloned outfit inherited place=slot and replaced the worn one."""

    import struct

    from test_xray_save import _base_item_state, _chunk, _object_record, _spawn, _state_base

    from editor.xray_container import lzo1x_compress
    from editor.xray_save import CS_FORMAT, _reset_added_item_state, parse_xray

    version, outer = 122, 5
    actor = _spawn("actor", 0, 0xFFFF, version, _state_base(version, money=1234), struct.pack("<H", 0))
    worn = b"\x02\x01\x00\x00\x80\x3f\x00"  # client data: place 1 = slot
    item = _spawn("bandage_existing", 0x2345, 0, version, _base_item_state(version), struct.pack("<H", 0) + b"\x00", worn)
    objects = struct.pack("<I", 2) + _object_record(actor, struct.pack("<H", 0)) + _object_record(item, struct.pack("<H", 0) + b"\x00")
    raw = b"".join((
        _chunk(0, struct.pack("<I", outer)),
        _chunk(5, struct.pack("<Qff", 123456, 10.0, 1.0)),
        _chunk(1, b"\x00" * 8),
        _chunk(2, objects),
        _chunk(9, b"registry"),
    ))
    data = struct.pack("<III", 0xFFFFFFFF, outer, len(raw)) + lzo1x_compress(raw)

    fixed = parse_xray(_reset_added_item_state(data, CS_FORMAT, 0x2345), CS_FORMAT, with_inventory=True)
    obj = fixed.object_by_id(0x2345)
    assert fixed.container.raw[obj.client_data_offset + 1] == 3  # backpack


def test_items_in_a_level_stash_move_to_the_backpack_with_their_state() -> None:
    import struct

    from test_xray_save import _base_item_state, _chunk, _object_record, _spawn, _state_base

    from editor.xray_container import lzo1x_compress
    from editor.xray_save import COP_FORMAT, parse_xray, take_from_stash, xray_stashes

    version, outer = 128, 6
    actor = _spawn("actor", 0, 0xFFFF, version, _state_base(version, money=1234), struct.pack("<H", 0))
    box = _spawn("inventory_box", 0x10, 0xFFFF, version, _base_item_state(version), struct.pack("<H", 0) + b"\x00", name_replace="zat_actor_stash")
    item = _spawn("bandage_existing", 0x2345, 0x10, version, _base_item_state(version), struct.pack("<H", 0) + b"\x00")
    objects = struct.pack("<I", 3) + b"".join(
        _object_record(spawn, struct.pack("<H", 0) + (b"\x00" if index else b""))
        for index, spawn in enumerate((actor, box, item))
    )
    raw = b"".join((
        _chunk(0, struct.pack("<I", outer)),
        _chunk(5, struct.pack("<Qff", 123456, 10.0, 1.0)),
        _chunk(1, b"\x00" * 8),
        _chunk(2, objects),
        _chunk(9, b"registry"),
    ))
    data = struct.pack("<III", 0xFFFFFFFF, outer, len(raw)) + lzo1x_compress(raw)

    parsed = parse_xray(data, COP_FORMAT, with_inventory=True)
    (stash,) = xray_stashes(parsed)
    assert (stash.name, stash.level, [i.object_id for i in stash.items]) == ("zat_actor_stash", "Затон", [0x2345])

    moved = parse_xray(take_from_stash(data, COP_FORMAT, 0x2345), COP_FORMAT, with_inventory=True)
    assert moved.object_by_id(0x2345).parent_id == moved.actor_id
    assert xray_stashes(moved) == ()
    with pytest.raises(Exception, match="не лежит в тайнике"):
        take_from_stash(data, COP_FORMAT, 0x0)
