from __future__ import annotations

import struct

import pytest
from test_xray_save import _fixture, _plan

from editor.catalog import FactionCatalog, FactionDefinition
from editor.models import EditPlan
from editor.xray_relations import parse_relation_registry
from editor.xray_save import (
    COP_FORMAT,
    XRaySaveError,
    inspect_xray,
    parse_xray,
    prepare_xray,
)


def _row(character_id: int, communities: tuple[tuple[int, int], ...]) -> bytes:
    personal = ((0x22, -7),)
    return (
        struct.pack("<H", character_id)
        + struct.pack("<I", len(personal))
        + b"".join(struct.pack("<Hi", key, value) for key, value in personal)
        + struct.pack("<I", len(communities))
        + b"".join(struct.pack("<ii", key, value) for key, value in communities)
    )


def _registry(
    actor_values: tuple[tuple[int, int], ...] = ((0, 100), (1, -100)),
) -> bytes:
    return (
        struct.pack("<I", 0)
        + struct.pack("<I", 2)
        + _row(0, actor_values)
        + _row(0x99, ((0, 25),))
        + b"REGISTRY-TAIL"
    )


def _catalog() -> FactionCatalog:
    return FactionCatalog(
        release_id="stalker-cop",
        source_root=None,
        factions=(
            FactionDefinition("actor", "Actor", "fixture", "stalker-cop", 0),
            FactionDefinition("bandit", "Bandit", "fixture", "stalker-cop", 1),
        ),
        goodwill_min=-3000,
        goodwill_max=1000,
    )


def test_relation_parser_stops_at_second_map_and_preserves_tail() -> None:
    payload = _registry()
    parsed = parse_relation_registry(payload, "stalker-cop")

    assert parsed.relation_count == 2
    assert parsed.for_character(0).personal == ((0x22, -7),)
    assert tuple((row.community_index, row.value) for row in parsed.for_character(0).communities) == (
        (0, 100),
        (1, -100),
    )
    assert payload[parsed.relations_end_offset:] == b"REGISTRY-TAIL"


def test_xray_relation_edit_patches_actor_row_only() -> None:
    data = _fixture(registry=_registry())
    before = parse_xray(data, COP_FORMAT)
    assert before.faction_relations == ((0, 100), (1, -100))
    assert before.relation_registry is not None
    assert inspect_xray(data, COP_FORMAT).faction_relations_editable is True
    assert inspect_xray(data, COP_FORMAT).faction_relations == before.faction_relations

    prepared = prepare_xray(
        data,
        EditPlan(source=_plan(data).source, faction_relations=(("bandit", 375),)),
        COP_FORMAT,
        faction_catalog=_catalog(),
    )
    after = parse_xray(prepared.data, COP_FORMAT)

    assert after.faction_relations == ((0, 100), (1, 375))
    assert after.relation_registry is not None
    assert before.relation_registry is not None
    assert after.relation_registry.for_character(0x99) == before.relation_registry.for_character(0x99)
    assert prepared.data != data


def test_xray_relation_edit_can_add_missing_community_row() -> None:
    data = _fixture(registry=_registry(((0, 100),)))
    prepared = prepare_xray(
        data,
        EditPlan(source=_plan(data).source, faction_relations=(("bandit", 250),)),
        COP_FORMAT,
        faction_catalog=_catalog(),
    )

    assert parse_xray(prepared.data, COP_FORMAT).faction_relations == ((0, 100), (1, 250))


def test_xray_relation_edit_rejects_unknown_key_and_out_of_range_value() -> None:
    data = _fixture(registry=_registry())
    with pytest.raises(XRaySaveError, match="отсутствует|catalog"):
        prepare_xray(
            data,
            EditPlan(source=_plan(data).source, faction_relations=(("dolg", 100),)),
            COP_FORMAT,
            faction_catalog=_catalog(),
        )
    with pytest.raises(XRaySaveError, match="goodwill|диапазон"):
        prepare_xray(
            data,
            EditPlan(source=_plan(data).source, faction_relations=(("bandit", 1001),)),
            COP_FORMAT,
            faction_catalog=_catalog(),
        )
