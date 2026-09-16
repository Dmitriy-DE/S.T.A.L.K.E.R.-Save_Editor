from __future__ import annotations

import hashlib
import struct

import pytest
from test_xray_durability import _condition_fixture, _condition_state
from test_xray_save import _chunk, _item_state, _object_record, _spawn, _state_base

from editor.models import EditPlan, SourceRef
from editor.xray_container import lzo1x_compress
from editor.xray_delete import analyze_xray_delete
from editor.xray_save import COP_FORMAT, XRaySaveError, parse_xray, prepare_xray


def _source(data: bytes) -> SourceRef:
    return SourceRef(
        kind="local",
        locator="delete-fixture.scop",
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _fixture_with_dependent_object() -> bytes:
    version = 128
    outer = 6
    actor = _spawn(
        "actor",
        0,
        0xFFFF,
        version,
        _state_base(version, money=1234),
        struct.pack("<H", 0),
    )
    parent_update = struct.pack("<H", 0) + b"\x00" * 6
    parent = _spawn(
        "wpn_parent",
        0x3456,
        0,
        version,
        _condition_state(version, 0.5),
        parent_update,
        b"\x02" + struct.pack("<HfB", 3 | (2 << 4) | (3 << 10), 0.5, 0),
    )
    child = _spawn(
        "ammo_child",
        0x4567,
        0x3456,
        version,
        _item_state(version, 1),
        struct.pack("<H", 0) + b"\x00" + struct.pack("<H", 1),
    )
    objects = struct.pack("<I", 3) + _object_record(actor, struct.pack("<H", 0))
    objects += _object_record(parent, parent_update) + _object_record(
        child,
        struct.pack("<H", 0) + b"\x00" + struct.pack("<H", 1),
    )
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


def test_delete_analysis_allows_a_leaf_inventory_object() -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=3 | (2 << 4) | (3 << 10),
    )
    parsed = parse_xray(data, COP_FORMAT)

    decision = analyze_xray_delete(parsed, parsed.inventory[0].handle)

    assert decision.allowed is True
    assert decision.blockers == ()
    assert decision.dependent_ids == ()


def test_delete_analysis_blocks_an_equipped_object_before_registry_write() -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=1 | (2 << 4) | (3 << 10),
    )
    parsed = parse_xray(data, COP_FORMAT)
    handle = parsed.inventory[0].handle

    decision = analyze_xray_delete(parsed, handle)

    assert decision.allowed is False
    assert any("equipped" in blocker for blocker in decision.blockers)
    with pytest.raises(XRaySaveError, match="equipped|экип"):
        prepare_xray(
            data,
            EditPlan(source=_source(data), detach=((handle, True),)),
            COP_FORMAT,
        )


def test_delete_analysis_blocks_objects_with_registry_dependents() -> None:
    data = _fixture_with_dependent_object()
    parsed = parse_xray(data, COP_FORMAT)

    decision = analyze_xray_delete(parsed, 0x3456)

    assert decision.allowed is False
    assert decision.dependent_ids == (0x4567,)
    assert any("dependent" in blocker for blocker in decision.blockers)
    with pytest.raises(XRaySaveError, match="dependent|ссыл|child"):
        prepare_xray(
            data,
            EditPlan(source=_source(data), detach=((0x3456, True),)),
            COP_FORMAT,
        )


def test_delete_analysis_blocks_a_missing_object_as_unresolved() -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=3 | (2 << 4) | (3 << 10),
    )
    parsed = parse_xray(data, COP_FORMAT)

    decision = analyze_xray_delete(parsed, 0x7777)

    assert decision.allowed is False
    assert decision.dependent_ids == ()
    assert any("unresolved" in blocker for blocker in decision.blockers)
    with pytest.raises(XRaySaveError, match="unresolved|missing"):
        prepare_xray(
            data,
            EditPlan(source=_source(data), detach=((0x7777, True),)),
            COP_FORMAT,
        )
