"""Bounded reader/writer for the original X-Ray relation registry.

The relation registry is part of the ALife registry container (chunk ``9``),
not part of the inventory object list.  Its first two maps are stable in the
official SoC, Clear Sky and CoP serializers: an InfoPortions map followed by a
character-id to ``RELATION_DATA`` map.  This module deliberately stops at the
end of that second map and preserves every later registry byte verbatim.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .xray_container import XRayError

_MAX_COUNT = 1_000_000
_MAX_STRING = 1 << 20


class XRayRelationError(XRayError):
    """Raised when the relation registry does not match an official layout."""


def _fail(message: str) -> XRayRelationError:
    return XRayRelationError(f"X-Ray relation registry: {message}")


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = bytes(data)
        self.pos = 0

    def _take(self, size: int) -> bytes:
        if size < 0 or self.pos + size > len(self.data):
            raise _fail(f"данные обрезаны на смещении 0x{self.pos:X}")
        start = self.pos
        self.pos += size
        return self.data[start : self.pos]

    def _unpack(self, fmt: str) -> int:
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise _fail(f"числовое поле обрезано на смещении 0x{self.pos:X}")
        value = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += size
        return int(value)

    def u16(self) -> int:
        return self._unpack("<H")

    def u32(self) -> int:
        return self._unpack("<I")

    def s32(self) -> int:
        return self._unpack("<i")

    def u64(self) -> int:
        return self._unpack("<Q")

    def zstring(self) -> str:
        end = self.data.find(b"\x00", self.pos)
        if end < 0 or end - self.pos > _MAX_STRING:
            raise _fail("строка InfoPortion не найдена или слишком длинная")
        value = self.data[self.pos : end]
        self.pos = end + 1
        return value.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class XRayGoodwillEntry:
    """One community goodwill value and its exact serialized value offset."""

    community_index: int
    value: int
    value_offset: int


@dataclass(frozen=True)
class XRayRelationEntry:
    """One character row in the relation registry."""

    character_id: int
    personal: tuple[tuple[int, int], ...]
    communities: tuple[XRayGoodwillEntry, ...]
    record_start: int
    record_end: int
    community_count_offset: int

    def community(self, community_index: int) -> XRayGoodwillEntry | None:
        return next(
            (
                entry
                for entry in self.communities
                if entry.community_index == community_index
            ),
            None,
        )


@dataclass(frozen=True)
class XRayRelationRegistry:
    """Parsed prefix of chunk 9 with no ownership of its raw tail."""

    release_id: str
    info_end_offset: int
    relation_count: int
    entries: tuple[XRayRelationEntry, ...]
    relations_end_offset: int

    def for_character(self, character_id: int) -> XRayRelationEntry:
        for entry in self.entries:
            if entry.character_id == character_id:
                return entry
        raise XRayRelationError(
            f"character id 0x{character_id:04X} отсутствует в relation registry"
        )


def _read_count(reader: _Reader, label: str) -> int:
    count = reader.u32()
    if count > _MAX_COUNT:
        raise _fail(f"{label} count={count} слишком велик")
    return count


def parse_relation_registry(payload: bytes, release_id: str) -> XRayRelationRegistry:
    """Parse InfoPortions and the following relation map from chunk 9."""

    reader = _Reader(payload)
    info_count = _read_count(reader, "InfoPortions")
    with_info_time = release_id != "stalker-cop"
    for _ in range(info_count):
        reader.u16()  # InfoPortion registry key
        values_count = _read_count(reader, "InfoPortion vector")
        for _ in range(values_count):
            reader.zstring()
            if with_info_time:
                reader.u64()
    info_end_offset = reader.pos

    relation_count = _read_count(reader, "relation")
    entries: list[XRayRelationEntry] = []
    seen_characters: set[int] = set()
    for _ in range(relation_count):
        record_start = reader.pos
        character_id = reader.u16()
        if character_id in seen_characters:
            raise _fail(f"повторяющийся character id 0x{character_id:04X}")
        seen_characters.add(character_id)

        personal_count = _read_count(reader, "personal relation")
        personal: list[tuple[int, int]] = []
        seen_personal: set[int] = set()
        for _ in range(personal_count):
            target_id = reader.u16()
            value = reader.s32()
            if target_id in seen_personal:
                raise _fail(
                    f"character 0x{character_id:04X}: повторяющийся personal id "
                    f"0x{target_id:04X}"
                )
            seen_personal.add(target_id)
            personal.append((target_id, value))

        community_count_offset = reader.pos
        community_count = _read_count(reader, "community relation")
        communities: list[XRayGoodwillEntry] = []
        seen_communities: set[int] = set()
        for _ in range(community_count):
            community_index = reader.s32()
            value_offset = reader.pos
            value = reader.s32()
            if community_index in seen_communities:
                raise _fail(
                    f"character 0x{character_id:04X}: повторяющийся community "
                    f"{community_index}"
                )
            seen_communities.add(community_index)
            communities.append(
                XRayGoodwillEntry(community_index, value, value_offset)
            )
        entries.append(
            XRayRelationEntry(
                character_id=character_id,
                personal=tuple(personal),
                communities=tuple(communities),
                record_start=record_start,
                record_end=reader.pos,
                community_count_offset=community_count_offset,
            )
        )

    return XRayRelationRegistry(
        release_id=release_id,
        info_end_offset=info_end_offset,
        relation_count=relation_count,
        entries=tuple(entries),
        relations_end_offset=reader.pos,
    )


def patch_relation_registry(
    payload: bytes,
    registry: XRayRelationRegistry,
    *,
    character_id: int,
    community_index: int,
    goodwill: int,
) -> bytes:
    """Patch one goodwill or extend only the actor's existing relation row."""

    if not -0x80000000 <= goodwill <= 0x7FFFFFFF:
        raise _fail("goodwill не помещается в signed s32")
    if not -0x80000000 <= community_index <= 0x7FFFFFFF:
        raise _fail("community index не помещается в signed s32")
    entry = registry.for_character(character_id)
    raw = bytes(payload)
    if not 0 <= entry.record_start < entry.record_end <= len(raw):
        raise _fail("граница relation record выходит за chunk")
    existing = entry.community(community_index)
    if existing is not None:
        if existing.value_offset + 4 > len(raw):
            raise _fail("goodwill value offset выходит за chunk")
        result = bytearray(raw)
        struct.pack_into("<i", result, existing.value_offset, goodwill)
        return bytes(result)

    new_communities = sorted(
        [
            (community.community_index, community.value)
            for community in entry.communities
        ]
        + [(community_index, goodwill)],
        key=lambda value: value[0],
    )
    if not (
        entry.record_start <= entry.community_count_offset <= entry.record_end
    ):
        raise _fail("community count offset выходит за relation record")
    prefix = raw[entry.record_start : entry.community_count_offset]
    replacement = struct.pack("<I", len(new_communities)) + b"".join(
        struct.pack("<ii", index, value) for index, value in new_communities
    )
    return (
        raw[: entry.record_start]
        + prefix
        + replacement
        + raw[entry.record_end :]
    )


__all__ = [
    "XRayGoodwillEntry",
    "XRayRelationEntry",
    "XRayRelationError",
    "XRayRelationRegistry",
    "parse_relation_registry",
    "patch_relation_registry",
]
