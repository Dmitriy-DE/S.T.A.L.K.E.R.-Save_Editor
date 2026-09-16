from __future__ import annotations

import struct

import pytest
from test_xray_save import _fixture, _plan

from editor.catalog import FactionCatalog, FactionDefinition
from editor.models import EditPlan
from editor.xray_save import (
    COP_FORMAT,
    CS_FORMAT,
    SOC_FORMAT,
    XRaySaveError,
    inspect_xray,
    parse_xray,
    prepare_xray,
)


def _catalog(release_id: str) -> FactionCatalog:
    return FactionCatalog(
        release_id=release_id,
        source_root=None,
        factions=(
            FactionDefinition("actor", "Actor", "fixture", release_id, 0),
            FactionDefinition("bandit", "Bandit", "fixture", release_id, 1),
        ),
    )


@pytest.mark.parametrize(
    ("spec", "version", "outer"),
    (
        (SOC_FORMAT, 118, 3),
        (CS_FORMAT, 124, 5),
        (COP_FORMAT, 128, 6),
    ),
)
def test_xray_reads_player_community_from_actor_state(
    spec, version: int, outer: int
) -> None:
    data = _fixture(version=version, outer=outer, player_community=0)

    parsed = parse_xray(data, spec)
    info = inspect_xray(data, spec)

    assert parsed.player_faction_index == 0
    assert parsed.player_faction_offset is not None
    assert parsed.player_faction_editable is True
    assert info.player_faction_index == 0
    assert info.player_faction_editable is True


def test_xray_player_faction_writer_patches_only_signed_community_field() -> None:
    data = _fixture(version=128, outer=6, player_community=0)
    before = parse_xray(data, COP_FORMAT)
    actor_before = before.object_by_id(before.actor_id)
    assert before.player_faction_offset is not None
    relative = before.player_faction_offset - actor_before.state_offset

    prepared = prepare_xray(
        data,
        EditPlan(source=_plan(data).source, player_faction="bandit"),
        COP_FORMAT,
        faction_catalog=_catalog("stalker-cop"),
    )
    after = parse_xray(prepared.data, COP_FORMAT)
    actor_after = after.object_by_id(after.actor_id)

    assert after.player_faction_index == 1
    assert prepared.data != data
    before_state = before.state_bytes(actor_before)
    after_state = after.state_bytes(actor_after)
    assert before_state[:relative] == after_state[:relative]
    assert before_state[relative + 4 :] == after_state[relative + 4 :]
    assert struct.unpack_from("<i", after_state, relative)[0] == 1


def test_xray_player_faction_rejects_foreign_catalog_key() -> None:
    data = _fixture(version=128, outer=6, player_community=0)

    with pytest.raises(XRaySaveError, match="отсутствует|catalog"):
        prepare_xray(
            data,
            EditPlan(source=_plan(data).source, player_faction="dolg"),
            COP_FORMAT,
            faction_catalog=_catalog("stalker-cop"),
        )
