from __future__ import annotations

import hashlib
import struct

import pytest
from test_xray_durability import _condition_fixture

from editor.models import EditPlan, SourceRef
from editor.xray_save import (
    COP_FORMAT,
    CS_FORMAT,
    SOC_FORMAT,
    XRaySaveError,
    parse_xray,
    prepare_xray,
)


def _source(data: bytes) -> SourceRef:
    return SourceRef(
        kind="local",
        locator="placement-fixture.sav",
        sha256=hashlib.sha256(data).hexdigest(),
    )


@pytest.mark.parametrize(
    ("spec", "version", "outer", "client_place"),
    (
        (SOC_FORMAT, 118, 3, 3 | (2 << 4) | (3 << 10)),
        (CS_FORMAT, 124, 5, 3 | (2 << 4) | (3 << 10)),
        (COP_FORMAT, 128, 6, 1 | (2 << 4) | (3 << 10)),
    ),
)
def test_xray_reads_release_specific_inventory_place(
    spec, version: int, outer: int, client_place: int
) -> None:
    data = _condition_fixture(
        version=version,
        outer=outer,
        client_place=client_place,
    )

    item = parse_xray(data, spec).inventory[0]

    assert item.placement_editable is True
    assert item.placement_type == ("ruck" if client_place & 0x0F == 3 else "slot")
    assert item.placement_slot == 2
    assert item.placement_base_slot == 3
    assert item.storage == ("inventory" if client_place & 0x0F == 3 else "equipped")


@pytest.mark.parametrize(
    ("spec", "version", "outer", "client_place"),
    (
        (SOC_FORMAT, 118, 3, 3 | (2 << 4) | (3 << 10)),
        (CS_FORMAT, 124, 5, 3 | (2 << 4) | (3 << 10)),
        (COP_FORMAT, 128, 6, 1 | (2 << 4) | (3 << 10)),
    ),
)
def test_xray_prepare_moves_item_to_equipment_slot(
    spec, version: int, outer: int, client_place: int
) -> None:
    data = _condition_fixture(
        version=version,
        outer=outer,
        client_place=client_place,
    )
    handle = parse_xray(data, spec).inventory[0].handle

    # The item goes back to its own base slot (3), the one the game stored.
    prepared = prepare_xray(
        data,
        EditPlan(source=_source(data), placements=((handle, "slot", 3),)),
        spec,
    )
    item = parse_xray(prepared.data, spec).inventory[0]

    assert prepared.data != data
    assert item.placement_type == "slot"
    assert item.placement_slot == 3
    assert item.placement_base_slot == 3
    assert item.storage == "equipped"


def test_xray_placement_refuses_slots_and_belt_the_game_would_not_use() -> None:
    data = _condition_fixture(version=128, outer=6, client_place=3 | (2 << 4) | (3 << 10))
    handle = parse_xray(data, COP_FORMAT).inventory[0].handle
    for target in (("slot", 12), ("slot", 4), ("belt", None)):  # helmet, grenade, belt
        with pytest.raises(XRaySaveError, match="не кладёт"):
            prepare_xray(
                data,
                EditPlan(source=_source(data), placements=((handle, *target),)),
                COP_FORMAT,
            )


def test_xray_prepare_moves_item_to_belt_without_overwriting_slot_metadata() -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=1 | (2 << 4) | (3 << 10),
        name="af_medusa",  # only artefacts go on the belt
    )
    handle = parse_xray(data, COP_FORMAT).inventory[0].handle

    prepared = prepare_xray(
        data,
        EditPlan(source=_source(data), placements=((handle, "belt", None),)),
        COP_FORMAT,
    )
    item = parse_xray(prepared.data, COP_FORMAT).inventory[0]

    assert item.placement_type == "belt"
    assert item.placement_slot == 2
    assert item.placement_base_slot == 3
    assert item.storage == "inventory"


def test_xray_placement_rejects_missing_or_invalid_client_place() -> None:
    data = _condition_fixture(version=128, outer=6, client_place=None)
    handle = parse_xray(data, COP_FORMAT).inventory[0].handle

    with pytest.raises(XRaySaveError, match="placement|позици|client-data"):
        prepare_xray(
            data,
            EditPlan(source=_source(data), placements=((handle, "ruck", None),)),
            COP_FORMAT,
        )

    invalid = _condition_fixture(version=128, outer=6, client_place=0x0000)
    invalid_handle = parse_xray(invalid, COP_FORMAT).inventory[0].handle
    with pytest.raises(XRaySaveError, match="placement|позици"):
        prepare_xray(
            invalid,
            EditPlan(
                source=_source(invalid),
                placements=((invalid_handle, "slot", 2),),
            ),
            COP_FORMAT,
        )


def test_xray_placement_writer_changes_only_place_u16() -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=3 | (2 << 4) | (3 << 10),
    )
    parsed = parse_xray(data, COP_FORMAT)
    obj = parsed.object_by_id(parsed.inventory[0].handle)
    assert obj.placement_offset is not None
    before = parsed.container.raw

    prepared = prepare_xray(
        data,
        EditPlan(
            source=_source(data),
            placements=((obj.object_id, "slot", 3),),
        ),
        COP_FORMAT,
    )
    after = parse_xray(prepared.data, COP_FORMAT).container.raw

    assert before[: obj.placement_offset] == after[: obj.placement_offset]
    assert before[obj.placement_offset + 2 :] == after[obj.placement_offset + 2 :]
    assert (
        struct.unpack_from("<H", after, obj.placement_offset)[0]
        == 1 | (3 << 4) | (3 << 10)
    )
