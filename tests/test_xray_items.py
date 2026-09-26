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


def _stash_fixture(
    *,
    item_name: str = "bandage_existing",
    item_parent: int = 0,
    placement: int = 3,
    ammo: bool = False,
    upgrades: tuple[str, ...] = (),
) -> bytes:
    import struct

    from test_xray_save import (
        _base_item_state,
        _chunk,
        _item_state,
        _object_record,
        _spawn,
        _state_base,
        _z,
    )

    version, outer = 128, 6
    actor_id, box_id = 0, 0x10
    actor = _spawn("actor", actor_id, 0xFFFF, version, _state_base(version, money=1234), struct.pack("<H", 0))
    box = _spawn(
        "inventory_box", box_id, 0xFFFF, version, _base_item_state(version),
        struct.pack("<H", 0) + b"\x00", name_replace="zat_actor_stash",
    )
    state = bytearray(_item_state(version, 7) if ammo else _base_item_state(version))
    tail = 6 if ammo else 4
    state = state[:-tail] + struct.pack("<I", len(upgrades))
    state += b"".join(_z(value) for value in upgrades)
    if ammo:
        state += struct.pack("<H", 7)
    client_data = b"\x00" + struct.pack("<H", placement)
    item_update = struct.pack("<H", 0) + b"\x00"
    if ammo:
        item_update += struct.pack("<H", 7)
    item = _spawn(
        item_name, 0x2345, item_parent, version, bytes(state),
        item_update, client_data,
    )
    objects = struct.pack("<I", 3) + b"".join(
        _object_record(spawn, struct.pack("<H", 0) if index == 0 else item_update)
        for index, spawn in enumerate((actor, box, item))
    )
    raw = b"".join((
        _chunk(0, struct.pack("<I", outer)),
        _chunk(5, struct.pack("<Qff", 123456, 10.0, 1.0)),
        _chunk(1, b"\x00" * 8),
        _chunk(2, objects),
        _chunk(9, b"registry"),
    ))
    from editor.xray_container import lzo1x_compress

    return struct.pack("<III", 0xFFFFFFFF, outer, len(raw)) + lzo1x_compress(raw)


def test_put_to_stash_moves_backpack_item_and_preserves_state_and_upgrades() -> None:
    from editor.xray_save import COP_FORMAT, parse_xray, put_to_stash

    data = _stash_fixture(item_parent=0, upgrades=("upg_original",))
    before = parse_xray(data, COP_FORMAT, with_inventory=True)
    item_before = before.object_by_id(0x2345)
    assert item_before.placement_type == "ruck"
    assert item_before.upgrades == ("upg_original",)

    moved = parse_xray(put_to_stash(data, COP_FORMAT, 0x2345, 0x10), COP_FORMAT, with_inventory=True)
    item_after = moved.object_by_id(0x2345)

    assert item_after.parent_id == 0x10
    assert moved.state_bytes(item_after) == before.state_bytes(item_before)
    assert moved.update_bytes(item_after) == before.update_bytes(item_before)
    assert moved.container.raw[item_after.client_data_offset : item_after.client_data_end] == before.container.raw[
        item_before.client_data_offset : item_before.client_data_end
    ]


def test_put_to_stash_rejects_an_equipped_item() -> None:
    from editor.xray_save import COP_FORMAT, XRaySaveError, put_to_stash

    with pytest.raises(XRaySaveError, match="рюкзак|надет"):
        put_to_stash(_stash_fixture(item_parent=0, placement=0x411), COP_FORMAT, 0x2345, 0x10)


def test_put_to_stash_rejects_foreign_and_non_inventory_box_ids() -> None:
    from editor.xray_save import COP_FORMAT, XRaySaveError, put_to_stash

    data = _stash_fixture(item_parent=0)
    with pytest.raises(XRaySaveError, match="не найден"):
        put_to_stash(data, COP_FORMAT, 0x2345, 0x7777)
    with pytest.raises(XRaySaveError, match="inventory_box"):
        put_to_stash(data, COP_FORMAT, 0x2345, 0)


def test_edit_plan_can_add_a_template_clone_directly_to_a_stash() -> None:
    import struct

    from test_xray_save import _ammo_catalog

    from editor.xray_save import COP_FORMAT, parse_xray, prepare_xray

    data = _stash_fixture(
        item_name="ammo_existing", item_parent=0, placement=0x411, ammo=True, upgrades=("old_upgrade",)
    )
    before = parse_xray(data, COP_FORMAT, with_inventory=True)
    prepared = prepare_xray(
        data,
        EditPlan(source=_source(data), adds=(("ammo_new", 12, "stash:16"),)),
        COP_FORMAT,
        catalog=_ammo_catalog(),
    )
    after = parse_xray(prepared.data, COP_FORMAT, with_inventory=True)
    created = [obj for obj in after.objects if obj.object_id not in {item.object_id for item in before.objects}]
    added = next(obj for obj in created if obj.name == "ammo_new")

    assert added.parent_id == 0x10
    state_offset, state_count = __import__("editor.xray_save", fromlist=["_parse_ammo_state"])._parse_ammo_state(
        after.container.raw, added
    )
    assert state_count == 12
    update = after.update_bytes(added)
    assert struct.unpack_from("<H", update, len(update) - 2)[0] == 12
    assert struct.unpack_from("<H", after.container.raw, added.client_data_offset + 1)[0] & 0x0F == 3
    assert state_offset > added.state_offset
    assert __import__("editor.xray_save", fromlist=["_parse_upgrade_state_window"])._parse_upgrade_state_window(
        after.container.raw,
        state_offset=added.state_offset,
        state_end=added.state_end,
        version=added.version,
        label="added ammo",
    )[1] == ()


def test_stash_add_rejects_a_box_id_that_is_not_present_or_not_a_box() -> None:
    from test_xray_save import _ammo_catalog

    from editor.xray_save import COP_FORMAT, XRaySaveError, prepare_xray

    data = _stash_fixture(item_name="ammo_existing", item_parent=0, ammo=True)
    with pytest.raises(XRaySaveError, match="не найден"):
        prepare_xray(
            data,
            EditPlan(source=_source(data), adds=(("ammo_new", 1, "stash:30583"),)),
            COP_FORMAT,
            catalog=_ammo_catalog(),
        )
    with pytest.raises(XRaySaveError, match="inventory_box"):
        prepare_xray(
            data,
            EditPlan(source=_source(data), adds=(("ammo_new", 1, "stash:0"),)),
            COP_FORMAT,
            catalog=_ammo_catalog(),
        )


def test_stash_puts_is_a_valid_edit_plan_field() -> None:
    from editor.formats import by_id
    from editor.xray_save import COP_FORMAT, parse_xray

    data = _stash_fixture(item_parent=0)
    plan = EditPlan(source=_source(data), stash_puts=((0x2345, 0x10),))
    prepared = by_id(COP_FORMAT.id).prepare(data, plan)
    after = parse_xray(prepared.data, COP_FORMAT, with_inventory=True)

    assert plan.stash_puts == ((0x2345, 0x10),)
    assert after.object_by_id(0x2345).parent_id == 0x10
