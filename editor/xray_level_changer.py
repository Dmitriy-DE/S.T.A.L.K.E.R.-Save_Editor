"""Read-only parsing of the STATE suffix owned by X-Ray level changers.

The caller must first locate the end of the inherited space-restrictor state.
This module does not parse ``all.spawn`` framing or the inherited state prefix.
"""

from __future__ import annotations

from dataclasses import dataclass

from .xray_save import XRaySaveError, _Reader


@dataclass(frozen=True)
class XRayLevelChangerStateSuffix:
    """Fields read by ``CSE_ALifeLevelChanger::STATE_Read`` after its base."""

    object_version: int
    dest_game_vertex_id: int | None
    dest_level_vertex_id: int | None
    dest_position: tuple[float, float, float] | None
    dest_direction: tuple[float, float, float] | None
    dest_level_name: str
    dest_level_point_name: str
    silent: bool | None
    consumed_bytes: int


def parse_level_changer_state_suffix(
    packet_suffix: bytes,
    object_version: int,
) -> XRayLevelChangerStateSuffix:
    """Parse only the class-specific packet suffix defined by OpenXRay.

    ``object_version`` is the entity's ``m_wVersion``, not the save container
    or actor spawn version. Bytes belonging to the inherited base state must
    already have been consumed by the caller.
    """

    if (
        isinstance(object_version, bool)
        or not isinstance(object_version, int)
        or not 0 <= object_version <= 0xFFFF
    ):
        raise XRaySaveError("level changer STATE: invalid object version")

    reader = _Reader(packet_suffix, label="level changer STATE suffix")
    if object_version < 34:
        # The old implementation discards these words; their meanings are not
        # established as destination vertex ids by STATE_Read.
        reader.u32()
        reader.u32()
        game_vertex_id = None
        level_vertex_id = None
        position = None
        direction = None
    else:
        game_vertex_id = reader.u16()
        level_vertex_id = reader.u32()
        position = (reader.f32(), reader.f32(), reader.f32())
        if object_version <= 53:
            yaw = reader.f32()
            direction = (0.0, yaw, 0.0)
        else:
            direction = (reader.f32(), reader.f32(), reader.f32())

    level_name = reader.zstring_text()
    level_point_name = reader.zstring_text()
    silent = bool(reader.u8()) if object_version > 116 else None

    return XRayLevelChangerStateSuffix(
        object_version=object_version,
        dest_game_vertex_id=game_vertex_id,
        dest_level_vertex_id=level_vertex_id,
        dest_position=position,
        dest_direction=direction,
        dest_level_name=level_name,
        dest_level_point_name=level_point_name,
        silent=silent,
        consumed_bytes=reader.pos,
    )


__all__ = ["XRayLevelChangerStateSuffix", "parse_level_changer_state_suffix"]
