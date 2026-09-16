from __future__ import annotations

import hashlib
import struct

import pytest
from test_xray_durability import _condition_state
from test_xray_save import _chunk, _object_record, _spawn, _state_base, _z

from editor.catalog import UpgradeCatalog, UpgradeDefinition
from editor.models import EditPlan, SourceRef
from editor.xray_container import lzo1x_compress
from editor.xray_save import (
    COP_FORMAT,
    CS_FORMAT,
    SOC_FORMAT,
    XRaySaveError,
    parse_xray,
    prepare_xray,
)


def _upgrade_state(version: int, upgrades: tuple[str, ...]) -> bytes:
    state = bytearray(_condition_state(version, 0.75))
    if version <= 123:
        return bytes(state) + b"TAIL"
    del state[-4:]
    state += struct.pack("<I", len(upgrades))
    for upgrade in upgrades:
        state += _z(upgrade)
    return bytes(state) + b"TAIL"


def _upgrade_fixture(
    *,
    spec= COP_FORMAT,
    version: int = 128,
    upgrades: tuple[str, ...] = ("up_a_wpn_test", "legacy_unknown"),
) -> bytes:
    actor = _spawn(
        "actor",
        0,
        0xFFFF,
        version,
        _state_base(version, money=1234),
        struct.pack("<H", 0),
    )
    update = b"\x00\x00\x00\x00"
    item = _spawn(
        "wpn_test",
        0x3456,
        0,
        version,
        _upgrade_state(version, upgrades),
        update,
    )
    objects = (
        struct.pack("<I", 2)
        + _object_record(actor, struct.pack("<H", 0))
        + _object_record(item, update)
    )
    raw = b"".join(
        (
            _chunk(0, struct.pack("<I", next(iter(spec.outer_versions)))),
            _chunk(5, struct.pack("<Qff", 123456, 10.0, 1.0)),
            _chunk(1, b"\x00" * 8),
            _chunk(2, objects),
            _chunk(9, b"registry"),
        )
    )
    outer = next(iter(spec.outer_versions))
    return struct.pack("<III", 0xFFFFFFFF, outer, len(raw)) + lzo1x_compress(raw)


def _source(data: bytes) -> SourceRef:
    return SourceRef(
        kind="local",
        locator="upgrades-fixture.sav",
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _catalog(spec=COP_FORMAT, *keys: str) -> UpgradeCatalog:
    return UpgradeCatalog(
        release_id=spec.id,
        source_root=None,
        upgrades=tuple(
            UpgradeDefinition(
                key=key,
                display_name=key,
                category="weapon",
                item_key="wpn_test",
                source="fixture",
                release_id=spec.id,
            )
            for key in keys
        ),
    )


def test_xray_reads_equipment_upgrade_vector_and_exposes_editable_item() -> None:
    data = _upgrade_fixture()

    parsed = parse_xray(data, COP_FORMAT)
    obj = parsed.object_by_id(0x3456)

    assert obj.upgrades == ("up_a_wpn_test", "legacy_unknown")
    assert obj.upgrades_offset is not None
    assert obj.upgrades_end is not None
    assert obj.upgrades_end > obj.upgrades_offset
    assert parsed.inventory[0].upgrades == obj.upgrades
    assert parsed.inventory[0].upgrades_editable is True
    assert "upgrades" not in obj.unknown_fields


@pytest.mark.parametrize(
    ("spec", "version", "expected"),
    (
        (SOC_FORMAT, 118, None),
        (CS_FORMAT, 123, None),
        (CS_FORMAT, 124, ("up_a_wpn_test", "legacy_unknown")),
        (COP_FORMAT, 128, ("up_a_wpn_test", "legacy_unknown")),
    ),
)
def test_xray_upgrade_vector_boundary_is_versioned(spec, version: int, expected) -> None:
    data = _upgrade_fixture(spec=spec, version=version)

    item = parse_xray(data, spec).inventory[0]

    assert item.upgrades == expected
    assert item.upgrades_editable is (expected is not None)


def test_xray_upgrade_writer_supports_add_remove_clear_and_preserves_state_tail() -> None:
    data = _upgrade_fixture()
    catalog = _catalog(COP_FORMAT, "up_a_wpn_test", "up_c_wpn_test")

    prepared = prepare_xray(
        data,
        EditPlan(
            source=_source(data),
            upgrades=((0x3456, ("legacy_unknown", "up_c_wpn_test")),),
        ),
        COP_FORMAT,
        upgrade_catalog=catalog,
    )
    after = parse_xray(prepared.data, COP_FORMAT)
    obj = after.object_by_id(0x3456)

    assert after.inventory[0].upgrades == ("legacy_unknown", "up_c_wpn_test")
    assert after.container.raw[obj.upgrades_end : obj.state_end] == b"TAIL"
    assert after.money == 1234

    cleared = prepare_xray(
        prepared.data,
        EditPlan(
            source=_source(prepared.data),
            upgrades=((0x3456, ()),),
        ),
        COP_FORMAT,
        upgrade_catalog=catalog,
    )
    assert parse_xray(cleared.data, COP_FORMAT).inventory[0].upgrades == ()


def test_xray_upgrade_writer_rejects_new_unknown_and_foreign_catalog_keys() -> None:
    data = _upgrade_fixture()
    plan = EditPlan(
        source=_source(data),
        upgrades=((0x3456, ("new_unknown",)),),
    )

    with pytest.raises(XRaySaveError, match="upgrade|catalog|неизвест"):
        prepare_xray(
            data,
            plan,
            COP_FORMAT,
            upgrade_catalog=_catalog(COP_FORMAT, "up_a_wpn_test"),
        )

    with pytest.raises(XRaySaveError, match="release|catalog"):
        prepare_xray(
            data,
            EditPlan(
                source=_source(data),
                upgrades=((0x3456, ("up_a_wpn_test",)),),
            ),
            COP_FORMAT,
            upgrade_catalog=_catalog(CS_FORMAT, "up_a_wpn_test"),
        )


def test_edit_plan_freezes_and_validates_upgrade_vectors() -> None:
    data = _upgrade_fixture()
    staged = [(0x3456, ["up_a_wpn_test"])]
    plan = EditPlan(source=_source(data), upgrades=staged)
    staged[0][1].append("mutated")

    assert plan.upgrades == ((0x3456, ("up_a_wpn_test",)),)
    with pytest.raises(ValueError, match="upgrade"):
        EditPlan(
            source=_source(data),
            upgrades=((0x3456, ("duplicate", "duplicate")),),
        )
