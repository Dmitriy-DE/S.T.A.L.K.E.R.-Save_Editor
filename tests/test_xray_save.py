from __future__ import annotations

import hashlib
import struct

import pytest

from editor.catalog import ItemCatalog, ItemDefinition
from editor.models import EditPlan, SourceRef
from editor.xray_container import XRayContainer, lzo1x_compress
from editor.xray_save import (
    COP_FORMAT,
    CS_FORMAT,
    SOC_FORMAT,
    XRayItemAdd,
    XRaySaveError,
    inspect_xray,
    parse_xray,
    prepare_xray,
)


def _z(value: str) -> bytes:
    return value.encode("utf-8") + b"\x00"


def _state_base(version: int, *, money: int | None = None) -> bytes:
    # CSE_ALifeObject + CSE_ALifeDynamicObjectVisual + creature/trader actor
    # inheritance as serialized by the public X-Ray source.  The fixture only
    # needs the prefix through the money field; the remaining actor fields are
    # included so the parser can validate the actor state boundary.
    state = bytearray()
    state += struct.pack("<HfIII", 12, 1.5, 0, 34, 0)
    state += _z("[actor]")
    state += struct.pack("<II", 0, 0)
    state += _z("actor.ogf")
    state += b"\x00"  # CSE_Visual flags, version > 103
    state += b"\x01\x02\x03"  # team, squad, group
    state += struct.pack("<f", 1.0)
    state += struct.pack("<I", 0)  # dynamic out restrictions
    state += struct.pack("<I", 0)  # dynamic in restrictions
    state += struct.pack("<H", 0xFFFF)
    state += struct.pack("<Q", 0)
    if money is not None:
        state += struct.pack("<I", money)
        state += _z("")  # specific character
        state += struct.pack("<I", 0)  # trader flags
        state += _z("default")
        state += struct.pack("<iii", -1, -1, -1)
        state += _z("")  # raw character name
        if version > 124:
            state += b"\x01\x00"  # deadbody flags
        state += _z("$editor")  # PH skeleton startup animation
        state += b"\x00"  # skeleton flags
        state += struct.pack("<H", 0xFFFF)
        state += struct.pack("<H", 0xFFFF)  # actor holder id
    return bytes(state)


def _item_state(version: int, count: int) -> bytes:
    state = bytearray()
    state += struct.pack("<HfIII", 15, 2.0, 0, 56, 0)
    state += _z("[ammo]")
    state += struct.pack("<II", 0, 0)
    state += _z("ammo.ogf")
    state += b"\x00"  # visual flags
    state += struct.pack("<f", 1.0)  # condition
    if version > 123:
        state += struct.pack("<I", 0)  # empty upgrades
    state += struct.pack("<H", count)
    return bytes(state)


def _base_item_state(version: int) -> bytes:
    state = bytearray(_item_state(version, 1))
    del state[-2:]
    return bytes(state)


def _spawn(
    name: str,
    object_id: int,
    parent_id: int,
    version: int,
    state: bytes,
    update: bytes,
    client_data: bytes = b"",
) -> bytes:
    packet = bytearray(struct.pack("<H", 1))
    packet += _z(name) + _z("")
    packet += struct.pack("<BB", 0, 0xFE)
    packet += struct.pack("<6f", 0, 0, 0, 0, 0, 0)
    packet += struct.pack("<4H", 0, object_id, parent_id, 0xFFFF)
    packet += struct.pack("<H", 1 << 5)  # M_SPAWN_VERSION
    packet += struct.pack("<H", version)
    if version > 120:
        packet += struct.pack("<H", 1)  # single-player game type
    packet += struct.pack("<H", 0)  # script version
    packet += struct.pack("<H", len(client_data)) + client_data
    packet += struct.pack("<H", 0)  # spawn id
    packet += struct.pack("<H", len(state) + 2) + state
    assert len(packet) <= 0xFFFF
    return bytes(packet)


def _object_record(spawn: bytes, update: bytes) -> bytes:
    return struct.pack("<H", len(spawn)) + spawn + struct.pack("<H", len(update)) + update


def _chunk(kind: int, payload: bytes) -> bytes:
    return struct.pack("<II", kind, len(payload)) + payload


def _fixture(
    version: int = 128,
    outer: int = 6,
    *,
    registry: bytes = b"registry",
) -> bytes:
    actor = _spawn(
        "actor", 0, 0xFFFF, version, _state_base(version, money=1234), struct.pack("<H", 0)
    )
    ammo_update = struct.pack("<H", 0) + b"\x00" + struct.pack("<H", 30)
    ammo = _spawn(
        "ammo_9x39_pab9",
        0x1234,
        0,
        version,
        _item_state(version, 30),
        ammo_update,
    )
    objects = struct.pack("<I", 2) + _object_record(actor, struct.pack("<H", 0)) + _object_record(ammo, ammo_update)
    raw = b"".join(
        (
            _chunk(0, struct.pack("<I", outer)),
            _chunk(5, struct.pack("<Qff", 123456, 10.0, 1.0)),
            _chunk(1, b"\x00" * 8),
            _chunk(2, objects),
            _chunk(9, registry),
        )
    )
    return struct.pack("<III", 0xFFFFFFFF, outer, len(raw)) + lzo1x_compress(raw)


def _fixture_with_base_item(version: int = 128, outer: int = 6) -> bytes:
    actor = _spawn(
        "actor", 0, 0xFFFF, version, _state_base(version, money=1234), struct.pack("<H", 0)
    )
    base_update = struct.pack("<H", 0) + b"\x00"
    base = _spawn(
        "bandage_existing",
        0x2345,
        0,
        version,
        _base_item_state(version),
        base_update,
    )
    objects = struct.pack("<I", 2) + _object_record(actor, struct.pack("<H", 0)) + _object_record(base, base_update)
    raw = b"".join(
        (
            _chunk(0, struct.pack("<I", outer)),
            _chunk(5, struct.pack("<Qff", 123456, 10.0, 1.0)),
            _chunk(1, b"\x00" * 8),
            _chunk(2, objects),
            _chunk(9, b"registry"),
        )
    )
    return struct.pack("<III", 0xFFFFFFFF, outer, len(raw)) + lzo1x_compress(raw)


def _plan(data: bytes, *, money: int | None = None, stacks=()) -> EditPlan:
    return EditPlan(
        source=SourceRef(
            kind="local",
            locator="fixture.sav",
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        money=money,
        stacks=tuple(stacks),
    )


def test_xray_parser_reads_actor_money_and_confirmed_ammo_stack() -> None:
    data = _fixture()

    parsed = parse_xray(data, COP_FORMAT)
    info = inspect_xray(data, COP_FORMAT)

    assert parsed.actor_version == 128
    assert parsed.money == 1234
    assert [(item.type_key, item.count, item.editable_count) for item in info.inventory] == [
        ("ammo_9x39_pab9", 30, True)
    ]
    assert info.money == 1234
    assert info.crc_present is False
    assert info.integrity_name == "X-Ray LZO/container"


def test_xray_metadata_probe_does_not_materialize_the_full_registry() -> None:
    data = _fixture()

    parsed = parse_xray(data, COP_FORMAT, with_inventory=False)

    assert [obj.name for obj in parsed.objects] == ["actor"]
    assert parsed.inventory == ()
    assert parsed.owned_handles == ()


def test_xray_metadata_probe_rejects_truncated_object_registry() -> None:
    data = _fixture()
    container = XRayContainer.from_bytes(data)
    object_chunk = next(chunk for chunk in container.chunks if chunk.type == 2)
    spawn_size = struct.unpack_from("<H", object_chunk.data, 4)[0]
    actor_record_end = 4 + 2 + spawn_size
    update_size = struct.unpack_from("<H", object_chunk.data, actor_record_end)[0]
    actor_record_end += 2 + update_size
    truncated_objects = struct.pack("<I", 2) + object_chunk.data[4:actor_record_end]
    raw = b"".join(
        _chunk(chunk.type, truncated_objects if chunk.type == 2 else chunk.data)
        for chunk in container.chunks
    )
    broken = struct.pack("<III", 0xFFFFFFFF, container.version, len(raw)) + lzo1x_compress(raw)

    with pytest.raises(XRaySaveError, match="OBJECT|объект"):
        parse_xray(broken, COP_FORMAT, with_inventory=False)


def test_xray_prepare_edits_money_and_ammo_in_both_serialized_states() -> None:
    data = _fixture()
    plan = _plan(data, money=9876, stacks=((0x1234, 44),))

    prepared = prepare_xray(data, plan, COP_FORMAT)
    after = parse_xray(prepared.data, COP_FORMAT)

    assert prepared.data != data
    assert prepared.output_sha256 == hashlib.sha256(prepared.data).hexdigest()
    assert after.money == 9876
    assert after.object_by_id(0x1234).count == 44
    assert after.object_by_id(0x1234).update_count == 44
    assert parse_xray(data, COP_FORMAT).money == 1234


def test_xray_objects_expose_exact_spawn_state_update_windows() -> None:
    data = _fixture()
    parsed = parse_xray(data, COP_FORMAT)
    ammo = parsed.object_by_id(0x1234)

    assert ammo.spawn_end - ammo.spawn_offset == struct.unpack_from(
        "<H", parsed.container.raw, ammo.record_offset
    )[0]
    assert parsed.spawn_bytes(ammo) == parsed.container.raw[ammo.spawn_offset : ammo.spawn_end]
    assert parsed.state_bytes(ammo) == parsed.container.raw[ammo.state_offset : ammo.state_end]
    assert parsed.update_bytes(ammo) == parsed.container.raw[ammo.update_offset : ammo.update_end]
    assert ammo.record_end > ammo.record_offset
    assert "prototype" in ammo.unknown_fields


def _ammo_catalog() -> ItemCatalog:
    return ItemCatalog(
        "stalker-cop",
        None,
        (
            ItemDefinition(
                key="ammo_new",
                display_name="New ammo",
                category="ammo",
                unit_weight=0.1,
                width=1,
                height=1,
                max_stack=30,
                slots=("8",),
                prototype=b"fixture-prototype",
                source="fixture",
                class_name="AMMO",
                serialization_family="ammo",
            ),
        ),
    )


def test_xray_ammo_add_allocates_registry_record_and_round_trips() -> None:
    data = _fixture()
    plan = _plan(data)
    plan = EditPlan(
        source=plan.source,
        adds=(("ammo_new", 12, "inventory"),),
    )

    prepared = prepare_xray(data, plan, COP_FORMAT, catalog=_ammo_catalog())
    after = parse_xray(prepared.data, COP_FORMAT)

    added = tuple(item for item in after.inventory if item.type_key == "ammo_new")
    assert len(added) == 1
    assert added[0].count == 12
    assert added[0].editable_count is True
    assert len(after.objects) == 3
    assert prepared.data != data


def test_xray_add_clones_a_catalog_family_without_game_asset_bytes() -> None:
    data = _fixture_with_base_item()
    catalog = ItemCatalog(
        "stalker-cop",
        None,
        (
            ItemDefinition(
                key="bandage_new",
                display_name="New bandage",
                category="consumable",
                unit_weight=0.1,
                width=1,
                height=1,
                max_stack=None,
                slots=(),
                prototype=None,
                source="fixture",
                class_name="II_BANDG",
                serialization_family="base",
            ),
        ),
    )
    plan = EditPlan(
        source=_plan(data).source,
        adds=(("bandage_new", 2, "inventory"),),
    )

    prepared = prepare_xray(data, plan, COP_FORMAT, catalog=catalog)
    after = parse_xray(prepared.data, COP_FORMAT)

    added = tuple(item for item in after.inventory if item.type_key == "bandage_new")
    assert len(added) == 2
    assert all(item.count is None for item in added)
    assert len(after.objects) == 4
    assert prepared.data != data


def test_xray_remove_accepts_any_actor_owned_item_record() -> None:
    data = _fixture_with_base_item()
    plan = EditPlan(
        source=_plan(data).source,
        detach=((0x2345, True),),
    )

    prepared = prepare_xray(data, plan, COP_FORMAT)
    after = parse_xray(prepared.data, COP_FORMAT)

    assert after.inventory == ()
    assert len(after.objects) == 1


def test_xray_ammo_remove_deletes_only_the_owned_record() -> None:
    data = _fixture()
    plan = EditPlan(
        source=_plan(data).source,
        detach=((0x1234, True),),
    )

    prepared = prepare_xray(data, plan, COP_FORMAT, catalog=_ammo_catalog())
    after = parse_xray(prepared.data, COP_FORMAT)

    assert after.inventory == ()
    assert len(after.objects) == 1
    assert prepared.data != data


def test_xray_item_add_validates_request_shape() -> None:
    with pytest.raises(ValueError):
        XRayItemAdd(None, "", 1, "inventory")


def test_xray_noop_prepare_keeps_original_bytes() -> None:
    data = _fixture()

    prepared = prepare_xray(data, _plan(data), COP_FORMAT)

    assert prepared.data == data


@pytest.mark.parametrize("format_", (SOC_FORMAT, CS_FORMAT, COP_FORMAT))
def test_xray_specs_are_separate_and_outer_versions_do_not_cross_detect(format_) -> None:
    data = _fixture(format_.actor_versions and next(iter(format_.actor_versions)), next(iter(format_.outer_versions)))

    assert parse_xray(data, format_).spec is format_

    for other in (SOC_FORMAT, CS_FORMAT, COP_FORMAT):
        if other is format_:
            continue
        with pytest.raises(XRaySaveError):
            parse_xray(data, other)


def test_xray_edits_reject_structural_operations_and_oversized_ammo() -> None:
    data = _fixture()

    with pytest.raises(XRaySaveError, match="move|перемещ"):
        prepare_xray(
            data,
            EditPlan(
                source=SourceRef(
                    kind="local",
                    locator="fixture.sav",
                    sha256=hashlib.sha256(data).hexdigest(),
                ),
                moves=((0x1234, 1, 1),),
            ),
            COP_FORMAT,
        )

    with pytest.raises(XRaySaveError, match="65535|диапазон"):
        prepare_xray(data, _plan(data, stacks=((0x1234, 65536),)), COP_FORMAT)
