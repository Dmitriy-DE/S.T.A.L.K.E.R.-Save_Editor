from __future__ import annotations

import struct

import pytest

from editor.xray_level_changer import parse_level_changer_state_suffix
from editor.xray_save import XRaySaveError


def _zstring(value: str) -> bytes:
    return value.encode("ascii") + b"\x00"


def test_synthetic_level_changer_state_suffix_matches_openxray_version_118() -> None:
    position = (1.25, -2.5, 3.75)
    direction = (0.1, 0.2, 0.3)
    packet = (
        struct.pack("<HI6f", 0x1234, 0x23456789, *position, *direction)
        + _zstring("garbage")
        + _zstring("garbage_from_swamp")
        + b"\x01"
    )

    result = parse_level_changer_state_suffix(packet, 118)

    assert result.dest_game_vertex_id == 0x1234
    assert result.dest_level_vertex_id == 0x23456789
    assert result.dest_position == pytest.approx(position)
    assert result.dest_direction == pytest.approx(direction)
    assert result.dest_level_name == "garbage"
    assert result.dest_level_point_name == "garbage_from_swamp"
    assert result.silent is True
    assert result.consumed_bytes == len(packet)


def test_level_changer_version_53_reads_yaw_as_the_direction_y_component() -> None:
    position = (4.0, 5.0, 6.0)
    yaw = 1.5
    packet = (
        struct.pack("<HI4f", 9, 17, *position, yaw)
        + _zstring("level")
        + _zstring("point")
    )

    result = parse_level_changer_state_suffix(packet, 53)

    assert result.dest_game_vertex_id == 9
    assert result.dest_level_vertex_id == 17
    assert result.dest_position == pytest.approx(position)
    assert result.dest_direction == pytest.approx((0.0, yaw, 0.0))
    assert result.silent is None
    assert result.consumed_bytes == len(packet)


def test_pre_34_level_changer_keeps_legacy_target_words_uninterpreted() -> None:
    packet = (
        struct.pack("<II", 0xFFFFFFFF, 0xAABBCCDD)
        + _zstring("level")
        + _zstring("point")
    )

    result = parse_level_changer_state_suffix(packet, 33)

    assert result.dest_game_vertex_id is None
    assert result.dest_level_vertex_id is None
    assert result.dest_position is None
    assert result.dest_direction is None
    assert result.dest_level_name == "level"
    assert result.dest_level_point_name == "point"
    assert result.silent is None
    assert result.consumed_bytes == len(packet)


def test_truncated_level_changer_suffix_is_rejected() -> None:
    packet = (
        struct.pack("<HI6f", 9, 17, 1.0, 2.0, 3.0, 0.1, 0.2, 0.3)
        + _zstring("level")
        + _zstring("point")
    )

    with pytest.raises(XRaySaveError):
        parse_level_changer_state_suffix(packet, 118)
