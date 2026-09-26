"""Read and safely patch the original trilogy's X-Ray save objects.

The original games do not use the S.T.A.L.K.E.R. 2 GVAS/CRC container.  They
store a versioned chunk stream in a raw LZO1X payload.  This module keeps the
format-specific part small and explicit: it parses the common object envelope,
the actor money field, confirmed inventory condition fields, and the
``CSE_ALifeItemAmmo`` count fields documented in the public X-Ray source.
Unknown object state remains untouched.

Structural item edits use an official item catalog plus an existing registry
record from the same serializer family.  The save still remains the source of
the serialized state template; no game archive bytes are copied into output.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass, replace
from typing import Literal

from save_format import InventoryItem, SaveInfo

from .catalog import (
    FactionCatalog,
    ItemCatalog,
    ItemDefinition,
    UpgradeCatalog,
    catalog_from_items,
)
from .models import EditPlan, PreparedEdit
from .xray_container import XRayChunk, XRayContainer, XRayError
from .xray_delete import analyze_xray_delete, analyze_xray_deletes
from .xray_item_state import (
    CONDITION_FAMILIES,
    ConditionCodecError,
    PlacementCodecError,
    patch_condition,
    patch_placement,
    read_condition_anchor,
    read_placement_anchor,
)
from .xray_relations import (
    XRayRelationError,
    XRayRelationRegistry,
    parse_relation_registry,
    patch_relation_registry,
)
from .xray_slots import placement_allowed

_M_SPAWN = 1
_M_UPDATE = 0
_M_SPAWN_VERSION = 1 << 5
_MAX_OBJECTS = 1_000_000
_MAX_STRING = 1 << 20
_MAX_VECTOR = 1_000_000
_MAX_AMMO_COUNT = 0xFFFF


@dataclass(frozen=True)
class XRayFormatSpec:
    """One original-game family selected by its outer and spawn versions."""

    id: str
    title: str
    extension: str
    outer_versions: frozenset[int]
    actor_versions: frozenset[int]
    client_place_offset: int
    # Originals store the outer version again in the ALIFE header; the
    # Enhanced Editions use their own ALIFE numbers there.
    alife_versions: frozenset[int] = frozenset()
    # Byte strings the object chunk must / must not contain.  Clear Sky EE and
    # Call of Pripyat EE share every version number; their level names differ.
    object_markers: tuple[bytes, ...] = ()
    forbidden_object_markers: tuple[bytes, ...] = ()


SOC_FORMAT = XRayFormatSpec(
    id="stalker-soc",
    title="S.T.A.L.K.E.R.: Shadow of Chernobyl",
    extension=".sav",
    outer_versions=frozenset({3}),
    actor_versions=frozenset({118}),
    client_place_offset=1,
)
CS_FORMAT = XRayFormatSpec(
    id="stalker-cs",
    title="S.T.A.L.K.E.R.: Clear Sky",
    extension=".sav",
    outer_versions=frozenset({5}),
    actor_versions=frozenset({122, 123, 124}),
    client_place_offset=1,
)
COP_FORMAT = XRayFormatSpec(
    id="stalker-cop",
    title="S.T.A.L.K.E.R.: Call of Pripyat",
    extension=".scop",
    outer_versions=frozenset({6}),
    actor_versions=frozenset({128}),
    client_place_offset=1,
)
# Enhanced Editions (2026-09-26 evidence, docs/evidence/EE_FORMAT_2026-09-26.md):
# the same LZO container and chunk layout as the originals, own ALIFE version.
SOC_EE_FORMAT = XRayFormatSpec(
    id="stalker-soc-ee",
    title="S.T.A.L.K.E.R.: Shadow of Chornobyl — Enhanced Edition",
    extension=".sav",
    outer_versions=frozenset({3}),
    actor_versions=frozenset({118}),
    client_place_offset=1,
    alife_versions=frozenset({51}),
)
CS_EE_FORMAT = XRayFormatSpec(
    id="stalker-cs-ee",
    title="S.T.A.L.K.E.R.: Clear Sky — Enhanced Edition",
    extension=".scs",
    outer_versions=frozenset({6}),
    actor_versions=frozenset({128}),
    client_place_offset=1,
    alife_versions=frozenset({54}),
    object_markers=(b"marsh",),
    forbidden_object_markers=(b"zaton",),
)
COP_EE_FORMAT = XRayFormatSpec(
    id="stalker-cop-ee",
    title="S.T.A.L.K.E.R.: Call of Pripyat — Enhanced Edition",
    extension=".scop",
    outer_versions=frozenset({6}),
    actor_versions=frozenset({128}),
    client_place_offset=1,
    alife_versions=frozenset({54}),
    object_markers=(b"zaton",),
    forbidden_object_markers=(b"marsh",),
)
XRAY_FORMATS = (SOC_FORMAT, CS_FORMAT, COP_FORMAT)
XRAY_EE_FORMATS = (SOC_EE_FORMAT, CS_EE_FORMAT, COP_EE_FORMAT)


class XRaySaveError(XRayError):
    """Raised when a valid container is not a supported object save."""


def _fail(message: str) -> XRaySaveError:
    return XRaySaveError(f"X-Ray save: {message}")


@dataclass(frozen=True)
class XRayItemAdd:
    """Validated request shape for a registry-backed item addition."""

    handle: int | None
    item_key: str
    quantity: int
    destination: str

    def __post_init__(self) -> None:
        if self.handle is not None and not 1 <= self.handle <= 0xFFFE:
            raise ValueError("X-Ray item handle must be in the range 1…65534")
        if not self.item_key.strip():
            raise ValueError("X-Ray item key must be non-empty")
        if self.quantity < 1 or self.quantity > _MAX_AMMO_COUNT:
            raise ValueError(
                f"X-Ray item quantity must be in the range 1…{_MAX_AMMO_COUNT}"
            )
        if self.destination != "inventory":
            raise ValueError("X-Ray item destination must be 'inventory'")


class _Reader:
    """Bounds-checked little-endian reader for one serialized object state."""

    def __init__(self, data: bytes | bytearray, *, label: str = "payload") -> None:
        self.data = bytes(data)
        self.pos = 0
        self.label = label

    def _take(self, size: int) -> bytes:
        if size < 0 or self.pos + size > len(self.data):
            raise _fail(
                f"{self.label} обрезан на смещении 0x{self.pos:X} "
                f"(нужно {size} байт)"
            )
        start = self.pos
        self.pos += size
        return self.data[start : self.pos]

    def _unpack(self, fmt: str) -> int | float:
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise _fail(f"{self.label} обрезан на смещении 0x{self.pos:X}")
        value = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += size
        return value

    def u8(self) -> int:
        return int(self._unpack("<B"))

    def u16(self) -> int:
        return int(self._unpack("<H"))

    def u32(self) -> int:
        return int(self._unpack("<I"))

    def s32(self) -> int:
        return int(self._unpack("<i"))

    def u64(self) -> int:
        return int(self._unpack("<Q"))

    def f32(self) -> float:
        # X-Ray saves can legitimately retain non-finite placeholder values in
        # object transforms.  They are not edit anchors, so preserve the
        # serialized value instead of rejecting an otherwise readable registry.
        return float(self._unpack("<f"))

    def bytes(self, size: int) -> bytes:
        return self._take(size)

    def zstring(self) -> str:
        end = self.data.find(b"\x00", self.pos)
        if end < 0 or end - self.pos > _MAX_STRING:
            raise _fail(f"{self.label}: stringZ не найден или слишком длинный")
        value = self.data[self.pos : end]
        self.pos = end + 1
        return value.decode("utf-8", errors="replace")

    def zstring_text(self) -> str:
        """A display string: X-Ray stores player-visible text in cp1251."""

        start = self.pos
        self.zstring()
        value = self.data[start : self.pos - 1]
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.decode("cp1251", errors="replace")

    def vector_u16(self) -> None:
        count = self.u32()
        if count > _MAX_VECTOR:
            raise _fail(f"{self.label}: vector count={count} слишком велик")
        for _ in range(count):
            self.u16()


@dataclass(frozen=True)
class _SpawnRecord:
    name: str
    object_id: int
    parent_id: int
    version: int
    position: tuple[float, float, float]
    spawn_offset: int
    spawn_end: int
    client_data_offset: int | None
    client_data_end: int | None
    state_size: int
    state_start: int
    state_end: int


@dataclass(frozen=True)
class XRayObject:
    """One object registry entry with only proven patch anchors."""

    index: int
    object_id: int
    parent_id: int
    name: str
    version: int
    position: tuple[float, float, float]
    record_offset: int
    record_end: int
    spawn_offset: int
    spawn_end: int
    client_data_offset: int | None
    client_data_end: int | None
    state_size: int
    state_offset: int
    state_end: int
    update_offset: int
    update_end: int
    update_size: int
    condition: float | None = None
    condition_offset: int | None = None
    client_condition_offset: int | None = None
    update_condition_offset: int | None = None
    condition_family: str | None = None
    storage: Literal["equipped", "inventory"] | None = None
    count: int | None = None
    update_count: int | None = None
    ammo_state_offset: int | None = None
    ammo_update_offset: int | None = None
    upgrades: tuple[str, ...] | None = None
    upgrades_offset: int | None = None
    upgrades_end: int | None = None
    placement_type: Literal["slot", "belt", "ruck"] | None = None
    placement_slot: int | None = None
    placement_base_slot: int | None = None
    placement_offset: int | None = None
    unknown_fields: tuple[str, ...] = (
        "prototype",
        "durability",
        "upgrades",
        "inventory position",
    )


@dataclass(frozen=True)
class _ActorStateDetails:
    """Source-backed actor STATE anchors shared by all original releases."""

    money_offset: int
    money: int
    player_faction_offset: int | None
    player_faction_index: int | None
    health: float | None = None
    rank: int | None = None
    reputation: int | None = None
    character_name: str | None = None


@dataclass(frozen=True)
class XRaySave:
    """A parsed save and its format-specific, fixed-size edit anchors."""

    data: bytes
    container: XRayContainer
    spec: XRayFormatSpec
    actor_version: int
    actor_id: int
    money: int
    money_offset: int
    player_faction_index: int | None
    player_faction_offset: int | None
    player_faction_editable: bool
    faction_relations: tuple[tuple[int, int], ...]
    relation_registry: XRayRelationRegistry | None
    faction_relations_editable: bool
    game_time: int | None
    time_factor: float | None
    normal_time_factor: float | None
    level_name: str | None
    objects: tuple[XRayObject, ...]
    inventory: tuple[InventoryItem, ...]
    owned_handles: tuple[int, ...]
    unresolved_handles: tuple[int, ...]
    warnings: tuple[str, ...]
    actor_health: float | None = None
    actor_rank: int | None = None
    actor_reputation: int | None = None
    actor_name: str | None = None

    def object_by_id(self, object_id: int) -> XRayObject:
        for obj in self.objects:
            if obj.object_id == object_id:
                return obj
        raise XRaySaveError(f"X-Ray save: object 0x{object_id:04X} не найден")

    def spawn_bytes(self, obj: XRayObject) -> bytes:
        return self.container.raw[obj.spawn_offset : obj.spawn_end]

    def state_bytes(self, obj: XRayObject) -> bytes:
        return self.container.raw[obj.state_offset : obj.state_end]

    def update_bytes(self, obj: XRayObject) -> bytes:
        return self.container.raw[obj.update_offset : obj.update_end]


def _chunk_once(chunks: tuple[XRayChunk, ...], kind: int, *, required: bool = True) -> XRayChunk | None:
    matches = tuple(chunk for chunk in chunks if chunk.type == kind)
    if len(matches) > 1:
        raise _fail(f"chunk type={kind} встречается {len(matches)} раз(а), ожидался один")
    if not matches:
        if required:
            raise _fail(f"обязательный chunk type={kind} отсутствует")
        return None
    return matches[0]


def _read_alife_object_state(reader: _Reader, version: int) -> None:
    """Consume CSE_ALifeObject::STATE_Read for the supported version range."""

    if version >= 1:
        if version > 24:
            if version < 83:
                reader.f32()
        else:
            reader.u8()
        if version < 4:
            reader.u16()
        reader.u16()  # graph id
        reader.f32()  # distance
    if version >= 4:
        reader.u32()  # direct control
    if version >= 8:
        reader.u32()  # node id
    if 22 < version <= 79:
        reader.u16()  # legacy spawn id
    if 23 < version < 84:
        reader.zstring()  # legacy spawn control
    if version > 49:
        reader.u32()  # ALife flags
    if version > 57:
        reader.zstring()  # ini string
    if version > 61:
        reader.u32()  # story id
    if version > 111:
        reader.u32()  # spawn story id


def _read_dynamic_visual_state(reader: _Reader, version: int) -> None:
    _read_alife_object_state(reader, version)
    if version > 31:
        reader.zstring()
        if version > 103:
            reader.u8()


def _parse_actor_state_details(raw: bytes, obj: XRayObject) -> _ActorStateDetails:
    reader = _Reader(raw[obj.state_offset : obj.state_end], label="actor STATE")
    version = obj.version

    _read_dynamic_visual_state(reader, version)
    reader.u8()  # team
    reader.u8()  # squad
    reader.u8()  # group
    health: float | None = None
    if version > 18:
        health = reader.f32()
    if version < 32:
        reader.zstring()  # old visual_read branch
    if version > 87:
        reader.vector_u16()  # dynamic out restrictions
        reader.vector_u16()  # dynamic in restrictions
    if version > 94:
        reader.u16()  # killer id
    if version > 115:
        reader.u64()  # game death time

    # CSE_ALifeTraderAbstract follows the creature state in the actor's
    # multiple-inheritance serialization order.  The money field is the first
    # stable trader scalar for all supported original-game actor versions.
    if version > 19 and version < 108:
        reader.u32()  # removed events field in old versions
    if version > 62:
        money_offset = obj.state_offset + reader.pos
        money = reader.u32()
    else:
        raise _fail(f"actor spawn version {version}: money field не сериализуется")

    # CSE_ALifeTraderAbstract::STATE_Write from the public X-Ray source:
    # specific character, trader flags, profile, then community/rank/reputation.
    if version > 75 and version < 98:
        reader.s32()  # legacy specific-character index
    elif version >= 98:
        reader.zstring()
    if version > 77:
        reader.u32()  # trader flags
    if version > 81 and version < 96:
        reader.s32()  # legacy character profile index
    elif version > 95:
        reader.zstring()

    player_faction_offset: int | None = None
    player_faction_index: int | None = None
    if version > 85:
        player_faction_offset = obj.state_offset + reader.pos
        player_faction_index = reader.s32()
    rank: int | None = None
    reputation: int | None = None
    character_name: str | None = None
    if version > 86:
        rank = reader.s32()
        reputation = reader.s32()
    if version > 104:
        character_name = reader.zstring_text() or None
    if version > 124:
        reader.u8()  # deadbody can take
        reader.u8()  # deadbody closed

    return _ActorStateDetails(
        money_offset=money_offset,
        money=money,
        player_faction_offset=player_faction_offset,
        player_faction_index=player_faction_index,
        health=health if health is not None and 0.0 <= health <= 1.0 else None,
        rank=rank,
        reputation=reputation,
        character_name=character_name,
    )


def _parse_ammo_state_window(
    raw: bytes,
    *,
    state_offset: int,
    state_end: int,
    version: int,
    label: str,
) -> tuple[int, int]:
    reader = _Reader(raw[state_offset:state_end], label=label)
    _read_dynamic_visual_state(reader, version)
    if version > 52:
        reader.f32()  # condition
    if version > 123:
        count = reader.u32()
        if count > _MAX_VECTOR:
            raise _fail(f"{label}: upgrades count={count} слишком велик")
        for _ in range(count):
            reader.zstring()
    offset = state_offset + reader.pos
    count = reader.u16()
    return offset, count


def _parse_ammo_state(raw: bytes, obj: XRayObject) -> tuple[int, int]:
    return _parse_ammo_state_window(
        raw,
        state_offset=obj.state_offset,
        state_end=obj.state_end,
        version=obj.version,
        label=f"{obj.name} STATE",
    )


def _parse_upgrade_state_window(
    raw: bytes,
    *,
    state_offset: int,
    state_end: int,
    version: int,
    label: str,
) -> tuple[int, tuple[str, ...], int]:
    """Read the source-backed CSE_ALifeInventoryItem upgrade vector."""

    if version <= 123:
        raise _fail(f"{label}: m_upgrades отсутствует до spawn version 124")
    reader = _Reader(raw[state_offset:state_end], label=label)
    _read_dynamic_visual_state(reader, version)
    if version > 52:
        reader.f32()  # condition
    upgrades_offset = state_offset + reader.pos
    count = reader.u32()
    if count > _MAX_VECTOR:
        raise _fail(f"{label}: upgrades count={count} слишком велик")
    values = tuple(reader.zstring() for _ in range(count))
    return upgrades_offset, values, state_offset + reader.pos


def _parse_spawn(packet: bytes, packet_offset: int) -> _SpawnRecord:
    reader = _Reader(packet, label="SPAWN packet")
    if reader.u16() != _M_SPAWN:
        raise _fail("объект начинается не с M_SPAWN")
    name = reader.zstring()
    reader.zstring()  # name replacement
    reader.u8()  # game id
    reader.u8()  # respawn point
    position = (reader.f32(), reader.f32(), reader.f32())
    reader.f32()  # angle x
    reader.f32()  # angle y
    reader.f32()  # angle z
    reader.u16()  # respawn time
    object_id = reader.u16()
    parent_id = reader.u16()
    reader.u16()  # phantom id
    flags = reader.u16()
    if not flags & _M_SPAWN_VERSION:
        raise _fail(f"объект {name!r}: отсутствует M_SPAWN_VERSION")
    version = reader.u16()
    if version < 112:
        raise _fail(
            f"объект {name!r}: spawn version {version} ниже безопасно поддерживаемого 112"
        )
    if version > 120:
        reader.u16()  # game type
    if version > 69:
        reader.u16()  # script version
    client_data_offset: int | None = None
    client_data_end: int | None = None
    if version > 70:
        client_size = reader.u16() if version > 93 else reader.u8()
        if client_size > 256 * 1024:
            raise _fail(f"объект {name!r}: client data слишком велик")
        client_data_offset = packet_offset + reader.pos
        reader.bytes(client_size)
        client_data_end = packet_offset + reader.pos
    if version > 79:
        reader.u16()  # spawn id

    state_size = reader.u16()
    if state_size < 2:
        raise _fail(f"объект {name!r}: STATE size={state_size} меньше 2")
    state_start_rel = reader.pos
    state_end_rel = state_start_rel + state_size - 2
    if state_end_rel > len(packet):
        raise _fail(f"объект {name!r}: STATE выходит за SPAWN packet")
    reader.pos = state_end_rel
    if reader.pos != len(packet):
        raise _fail(f"объект {name!r}: после STATE остались байты")
    return _SpawnRecord(
        name=name,
        object_id=object_id,
        parent_id=parent_id,
        version=version,
        position=position,
        spawn_offset=packet_offset,
        spawn_end=packet_offset + len(packet),
        client_data_offset=client_data_offset,
        client_data_end=client_data_end,
        state_size=state_size,
        state_start=packet_offset + state_start_rel,
        state_end=packet_offset + state_end_rel,
    )


def _parse_objects(raw: bytes, chunk: XRayChunk) -> tuple[XRayObject, ...]:
    reader = _Reader(chunk.data, label="OBJECT chunk")
    count = reader.u32()
    if count == 0 or count > _MAX_OBJECTS:
        raise _fail(f"OBJECT count={count} вне диапазона")
    data_offset = chunk.offset + 8
    objects: list[XRayObject] = []
    seen_ids: set[int] = set()
    for index in range(count):
        record_offset = data_offset + reader.pos
        spawn_size = reader.u16()
        spawn_offset_rel = reader.pos
        spawn_packet = reader.bytes(spawn_size)
        spawn = _parse_spawn(spawn_packet, data_offset + spawn_offset_rel)
        update_size = reader.u16()
        update_offset_rel = reader.pos
        update_packet = reader.bytes(update_size)
        if len(update_packet) < 2 or struct.unpack_from("<H", update_packet, 0)[0] != _M_UPDATE:
            raise _fail(f"объект {spawn.name!r}: UPDATE не начинается с M_UPDATE")
        if spawn.object_id in seen_ids:
            raise _fail(f"повторяющийся object id 0x{spawn.object_id:04X}")
        seen_ids.add(spawn.object_id)
        update_offset = data_offset + update_offset_rel
        obj = XRayObject(
            index=index,
            object_id=spawn.object_id,
            parent_id=spawn.parent_id,
            name=spawn.name,
            version=spawn.version,
            position=spawn.position,
            record_offset=record_offset,
            record_end=data_offset + reader.pos,
            spawn_offset=spawn.spawn_offset,
            spawn_end=spawn.spawn_end,
            client_data_offset=spawn.client_data_offset,
            client_data_end=spawn.client_data_end,
            state_size=spawn.state_size,
            state_offset=spawn.state_start,
            state_end=spawn.state_end,
            update_offset=update_offset,
            update_end=update_offset + update_size,
            update_size=update_size,
        )
        objects.append(obj)
    if reader.pos != len(chunk.data):
        raise _fail(
            f"OBJECT chunk имеет {len(chunk.data) - reader.pos} лишних байт после {count} объектов"
        )
    return tuple(objects)


def _parse_actor_probe(
    raw: bytes,
    chunk: XRayChunk,
    *,
    strict: bool = True,
) -> XRayObject:
    """Read only enough of the registry to identify the actor.

    Format detection and metadata-only inspection do not need millions of
    object records materialized as Python dataclasses.  The original saves in
    the supported releases put the actor first; the loop remains defensive so
    a modded registry with another order still finds it.  Full inspection and
    all edits continue through :func:`_parse_objects` below.
    """

    reader = _Reader(chunk.data, label="OBJECT probe")
    count = reader.u32()
    if count == 0 or count > _MAX_OBJECTS:
        raise _fail(f"OBJECT count={count} вне диапазона")
    data_offset = chunk.offset + 8
    actor: XRayObject | None = None
    for index in range(count):
        record_offset = data_offset + reader.pos
        spawn_size = reader.u16()
        spawn_offset_rel = reader.pos
        spawn_end = spawn_offset_rel + spawn_size
        if spawn_end > len(chunk.data):
            raise _fail(f"OBJECT #{index}: SPAWN packet обрезан")
        name = ""
        if actor is None:
            name_end = chunk.data.find(b"\x00", spawn_offset_rel + 2, spawn_end)
            if name_end < 0:
                raise _fail(f"OBJECT #{index}: SPAWN name не найден")
            name = chunk.data[spawn_offset_rel + 2 : name_end].decode(
                "utf-8", errors="replace"
            )
        reader.pos = spawn_end
        update_size = reader.u16()
        update_offset_rel = reader.pos
        update_end = update_offset_rel + update_size
        if update_size < 2 or update_end > len(chunk.data):
            raise _fail(f"объект {name!r}: UPDATE packet обрезан")
        if struct.unpack_from("<H", chunk.data, update_offset_rel)[0] != _M_UPDATE:
            raise _fail(f"объект {name!r}: UPDATE не начинается с M_UPDATE")
        reader.pos = update_end
        if name.lower() == "actor":
            spawn_packet = chunk.data[spawn_offset_rel:spawn_end]
            spawn = _parse_spawn(spawn_packet, data_offset + spawn_offset_rel)
            actor = XRayObject(
                index=index,
                object_id=spawn.object_id,
                parent_id=spawn.parent_id,
                name=spawn.name,
                version=spawn.version,
                position=spawn.position,
                record_offset=record_offset,
                record_end=data_offset + reader.pos,
                spawn_offset=spawn.spawn_offset,
                spawn_end=spawn.spawn_end,
                client_data_offset=spawn.client_data_offset,
                client_data_end=spawn.client_data_end,
                state_size=spawn.state_size,
                state_offset=spawn.state_start,
                state_end=spawn.state_end,
                update_offset=data_offset + update_offset_rel,
                update_end=data_offset + update_offset_rel + update_size,
                update_size=update_size,
            )
            if not strict:
                return actor
    if reader.pos != len(chunk.data):
        raise _fail(
            f"OBJECT chunk имеет {len(chunk.data) - reader.pos} лишних байт "
            f"после {count} объектов"
        )
    if actor is None:
        raise _fail("OBJECT registry не содержит actor")
    return actor


def _category_for_name(name: str) -> tuple[int, str]:
    """Return a UI-only category inferred from the serialized section prefix."""

    lowered = name.lower()
    if lowered.startswith("ammo_"):
        return 5, "Патроны"
    if lowered.startswith(("wpn_", "weapon_")):
        return 0, "Оружие"
    if lowered.startswith(("outfit_", "scientific_", "helm_", "armor_")) or lowered.endswith(
        ("_outfit", "_helmet", "_helm", "_armor")
    ):
        return 1, "Броня/экипировка"
    if lowered.startswith(("af_", "artifact_")):
        return 2, "Артефакт"
    if lowered.startswith(("device_", "detector_")):
        return 8, "Устройство"
    if lowered.startswith(("grenade", "rgd", "f1_")):
        return 7, "Гранаты/стак"
    if lowered.startswith(
        ("medkit", "bandage", "antirad", "drug_", "food_", "bread", "kolbasa", "vodka", "energy")
    ):
        return 4, "Расходник"
    return 8, "Разное"


def _inferred_serialization_family(name: str) -> str:
    """Infer only the stable serializer families from a serialized key.

    Catalog entries take precedence.  These fallbacks keep saves usable when a
    catalog is unavailable for an already-present object; they are not used to
    claim that an arbitrary key is an official item.
    """

    lowered = name.casefold()
    if lowered.startswith("ammo_"):
        return "ammo"
    if lowered == "device_torch":
        return "torch"
    if lowered == "device_pda":
        return "pda"
    if lowered.startswith(("detector_", "device_detector")):
        return "detector"
    if lowered.startswith(("outfit_", "scientific_", "helm_", "armor_")) or lowered.endswith(
        ("_outfit", "_helmet", "_helm", "_armor")
    ):
        return "outfit"
    if lowered.startswith(("wpn_", "weapon_")):
        if lowered.endswith("_knife"):
            return "weapon"
        if lowered in {"wpn_bm16", "wpn_rg6", "wpn_shotgun", "wpn_spas12", "wpn_toz34"}:
            return "weapon_shotgun"
        if lowered in {"wpn_ak74", "wpn_fn2000", "wpn_groza"}:
            return "weapon_wgl"
        return "weapon_magazined"
    return "base"


def _definition_serialization_family(definition: object) -> str:
    family = getattr(definition, "serialization_family", None)
    return str(family).casefold() if family else _inferred_serialization_family(
        str(getattr(definition, "key", ""))
    )


def _object_serialization_family(obj: XRayObject, catalog: ItemCatalog) -> str:
    definition = catalog.resolve(obj.name)
    if definition is not None:
        return _definition_serialization_family(definition)
    return _inferred_serialization_family(obj.name)


def catalog_from_save_inventory(
    spec: XRayFormatSpec,
    inventory: tuple[InventoryItem, ...],
) -> ItemCatalog:
    """Build a deliberately limited browser catalog from observed save keys.

    A browser cannot inspect a local Steam installation.  The resulting
    catalog therefore exposes only exact serialized keys already present in
    the selected save; it never pretends those entries came from an official
    resource archive.  Desktop catalog loading remains the path for adding a
    key that is not already observed in the save.
    """

    definitions: dict[str, ItemDefinition] = {}
    for item in inventory:
        key = item.type_key
        if key in definitions:
            continue
        family = _inferred_serialization_family(key)
        definitions[key] = ItemDefinition(
            key=key,
            display_name=item.display_name,
            category=item.category,
            unit_weight=item.unit_weight,
            width=item.width,
            height=item.height,
            max_stack=item.count_max if family == "ammo" else None,
            slots=(),
            prototype=None,
            source="save-observed",
            serialization_family=family,
        )
    return catalog_from_items(
        spec.id,
        tuple(definitions.values()),
    )


def _inventory_items(
    raw: bytes,
    objects: tuple[XRayObject, ...],
    actor_id: int,
) -> tuple[tuple[InventoryItem, ...], tuple[int, ...], tuple[int, ...], tuple[str, ...]]:
    children = tuple(obj for obj in objects if obj.parent_id == actor_id)
    items: list[InventoryItem] = []
    unresolved: list[int] = []
    warnings: list[str] = []
    for obj in children:
        kind, category = _category_for_name(obj.name)
        count = obj.count
        update_count = obj.update_count
        state_offset = obj.ammo_state_offset
        update_offset = obj.ammo_update_offset
        ammo = obj.name.lower().startswith("ammo_")
        anchors_ok = (
            state_offset is not None
            and update_offset is not None
            and count is not None
            and update_count is not None
        )
        if ammo and not anchors_ok:
            unresolved.append(obj.object_id)
            warnings.append(
                f"Handle 0x{obj.object_id:04X}: ammo count не разобран, только read-only"
        )
        editable = anchors_ok if ammo else False
        condition_editable = (
            obj.condition is not None
            and obj.condition_offset is not None
            and obj.condition_family in CONDITION_FAMILIES
        )
        if obj.condition_family in CONDITION_FAMILIES and not condition_editable:
            warnings.append(
                f"Handle 0x{obj.object_id:04X}: condition не разобран, только read-only"
            )
        items.append(
            InventoryItem(
                handle=obj.object_id,
                x=None,
                y=None,
                width=None,
                height=None,
                cells=(),
                count=count,
                total_weight=None,
                unit_weight=None,
                kind_code=kind,
                category=category,
                record_offset=obj.record_offset,
                record_end_guess=obj.record_end,
                fingerprint=hashlib.sha256(raw[obj.record_offset : obj.record_end]).hexdigest(),
                type_key=obj.name,
                editable_count=editable,
                display_name=obj.name,
                position_label=(
                    f"экипировано (слот {obj.placement_slot})"
                    if obj.placement_type == "slot" and obj.placement_slot is not None
                    else (
                        "пояс"
                        if obj.placement_type == "belt"
                        else (
                            "рюкзак"
                            if obj.placement_type == "ruck"
                            else (
                                "экипировано (слот подтверждён)"
                                if obj.storage == "equipped"
                                else (
                                    "инвентарь actor"
                                    if obj.storage == "inventory"
                                    else "инвентарь actor; слот не определён"
                                )
                            )
                        )
                    )
                ),
                size_label="неизвестно",
                count_max=_MAX_AMMO_COUNT,
                condition=obj.condition,
                condition_editable=condition_editable,
                storage=obj.storage,
                observation_source=(
                    "equipped" if obj.storage == "equipped" else "actor_inventory"
                ),
                upgrades=obj.upgrades,
                upgrades_editable=obj.upgrades is not None,
                placement_type=obj.placement_type,
                placement_slot=obj.placement_slot,
                placement_base_slot=obj.placement_base_slot,
                placement_editable=obj.placement_offset is not None,
            )
        )
    items.sort(key=lambda item: item.handle)
    warnings.append(
        "X-Ray: названия и категории предметов показаны по serialized section key; "
        "перевод, вес, размер и точная UI-сетка не извлечены"
    )
    return tuple(items), tuple(obj.object_id for obj in children), tuple(unresolved), tuple(warnings)


def _annotate_inventory_deletion(
    parsed: XRaySave,
    inventory: tuple[InventoryItem, ...],
) -> tuple[InventoryItem, ...]:
    """Expose the same known-reference delete gate used by the writer."""

    decisions = analyze_xray_deletes(parsed, (item.handle for item in inventory))
    annotated: list[InventoryItem] = []
    for item in inventory:
        decision = decisions[item.handle]
        annotated.append(
            replace(
                item,
                remove_editable=decision.allowed,
                remove_reason=None if decision.allowed else decision.message,
            )
        )
    return tuple(annotated)


def _annotate_ammo_objects(raw: bytes, objects: tuple[XRayObject, ...], actor_id: int) -> tuple[XRayObject, ...]:
    annotated: list[XRayObject] = []
    for obj in objects:
        if obj.parent_id != actor_id or not obj.name.lower().startswith("ammo_"):
            annotated.append(obj)
            continue
        try:
            state_offset, count = _parse_ammo_state(raw, obj)
            if obj.update_end - obj.update_offset < 5:
                raise _fail(f"{obj.name}: UPDATE слишком короткий для ammo count")
            update_offset = obj.update_end - 2
            update_count = struct.unpack_from("<H", raw, update_offset)[0]
        except XRaySaveError:
            annotated.append(obj)
        else:
            annotated.append(
                replace(
                    obj,
                    count=count,
                    update_count=update_count,
                    ammo_state_offset=state_offset,
                    ammo_update_offset=update_offset,
                )
            )
    return tuple(annotated)


def _annotate_inventory_conditions(
    raw: bytes,
    objects: tuple[XRayObject, ...],
    actor_id: int,
) -> tuple[XRayObject, ...]:
    """Attach only source-confirmed STATE/UPDATE condition anchors."""

    annotated: list[XRayObject] = []
    for obj in objects:
        if obj.parent_id != actor_id:
            annotated.append(obj)
            continue
        family = _inferred_serialization_family(obj.name)
        if family not in CONDITION_FAMILIES:
            annotated.append(obj)
            continue
        try:
            anchor = read_condition_anchor(raw, obj, family)
        except ConditionCodecError:
            annotated.append(obj)
            continue
        known_fields = tuple(
            field for field in obj.unknown_fields if field != "durability"
        )
        annotated.append(
            replace(
                obj,
                condition=anchor.value,
                condition_offset=anchor.state_offset,
                client_condition_offset=anchor.client_offset,
                update_condition_offset=anchor.update_offset,
                condition_family=family,
                storage=anchor.storage if anchor.storage is not None else obj.storage,
                unknown_fields=known_fields,
            )
        )
    return tuple(annotated)


def _annotate_inventory_placements(
    raw: bytes,
    objects: tuple[XRayObject, ...],
    actor_id: int,
    client_place_offset: int,
) -> tuple[XRayObject, ...]:
    """Attach a place only at the exact client-data offset for this release."""

    annotated: list[XRayObject] = []
    for obj in objects:
        if obj.parent_id != actor_id:
            annotated.append(obj)
            continue
        try:
            anchor = read_placement_anchor(raw, obj, client_place_offset)
        except PlacementCodecError:
            annotated.append(obj)
            continue
        known_fields = tuple(
            field for field in obj.unknown_fields if field != "inventory position"
        )
        annotated.append(
            replace(
                obj,
                placement_type=anchor.placement_type,
                placement_slot=anchor.slot_id,
                placement_base_slot=anchor.base_slot_id,
                placement_offset=anchor.offset,
                storage=anchor.storage,
                unknown_fields=known_fields,
            )
        )
    return tuple(annotated)


def _annotate_inventory_upgrades(
    raw: bytes,
    objects: tuple[XRayObject, ...],
    actor_id: int,
) -> tuple[XRayObject, ...]:
    """Attach exact upgrade-vector boundaries for actor-owned X-Ray items."""

    annotated: list[XRayObject] = []
    for obj in objects:
        if obj.parent_id != actor_id or obj.version <= 123:
            annotated.append(obj)
            continue
        try:
            upgrades_offset, upgrades, upgrades_end = _parse_upgrade_state_window(
                raw,
                state_offset=obj.state_offset,
                state_end=obj.state_end,
                version=obj.version,
                label=f"{obj.name} STATE",
            )
        except XRaySaveError:
            annotated.append(obj)
            continue
        known_fields = tuple(
            field for field in obj.unknown_fields if field != "upgrades"
        )
        annotated.append(
            replace(
                obj,
                upgrades=upgrades,
                upgrades_offset=upgrades_offset,
                upgrades_end=upgrades_end,
                unknown_fields=known_fields,
            )
        )
    return tuple(annotated)


def parse_xray(
    data: bytes,
    spec: XRayFormatSpec,
    *,
    with_inventory: bool = True,
    strict_registry: bool = True,
) -> XRaySave:
    """Parse one supported original-game save without modifying its bytes.

    ``strict_registry=False`` is only for cheap candidate detection while
    listing local files.  It stops after the actor record; opening a save and
    every edit keep the default full registry validation.
    """

    payload = bytes(data)
    try:
        container = XRayContainer.from_bytes(payload)
    except XRayError as exc:
        raise _fail(str(exc)) from exc
    if container.version not in spec.outer_versions:
        expected = ", ".join(str(v) for v in sorted(spec.outer_versions))
        raise _fail(
            f"outer version {container.version} не относится к {spec.id}; ожидалось {expected}"
        )

    chunks = container.chunks
    header_chunk = _chunk_once(chunks, 0)
    assert header_chunk is not None
    if len(header_chunk.data) != 4:
        raise _fail("ALIFE header chunk должен содержать ровно u32 version")
    alife_version = struct.unpack_from("<I", header_chunk.data, 0)[0]
    expected_alife = spec.alife_versions or frozenset({container.version})
    if alife_version not in expected_alife:
        raise _fail(
            f"ALIFE chunk version {alife_version} не совпадает с outer version {container.version}"
        )

    time_chunk = _chunk_once(chunks, 5)
    assert time_chunk is not None
    if len(time_chunk.data) < 16:
        raise _fail("GAME_TIME chunk короче 16 байт")
    game_time, time_factor, normal_time_factor = struct.unpack_from("<Qff", time_chunk.data, 0)
    if not math.isfinite(time_factor) or not math.isfinite(normal_time_factor):
        raise _fail("GAME_TIME содержит нечисловой time factor")

    spawn_chunk = _chunk_once(chunks, 1)
    assert spawn_chunk is not None
    level_name: str | None = None
    try:
        spawn_subchunks = parse_subchunks(spawn_chunk.data)
        spawn_header = _chunk_once(spawn_subchunks, 0, required=False)
        if spawn_header is not None:
            level_reader = _Reader(spawn_header.data, label="SPAWN header")
            level_name = level_reader.zstring()
    except XRaySaveError:
        # The object and time chunks remain independently parseable.  Keep the
        # save usable while making the absent level metadata visible to callers.
        level_name = None

    object_chunk = _chunk_once(chunks, 2)
    assert object_chunk is not None
    for marker in spec.object_markers:
        if marker not in object_chunk.data:
            raise _fail(f"нет признака {marker.decode()!r} для {spec.id}")
    for marker in spec.forbidden_object_markers:
        if marker in object_chunk.data:
            raise _fail(f"признак {marker.decode()!r} другой игры, не {spec.id}")
    objects = (
        _parse_objects(container.raw, object_chunk)
        if with_inventory
        else (
            _parse_actor_probe(
                container.raw,
                object_chunk,
                strict=strict_registry,
            ),
        )
    )
    actors = tuple(obj for obj in objects if obj.name.lower() == "actor")
    if len(actors) != 1:
        raise _fail(f"найдено actor объектов: {len(actors)}, ожидался ровно один")
    actor = actors[0]
    if actor.version not in spec.actor_versions:
        expected = ", ".join(str(v) for v in sorted(spec.actor_versions))
        raise _fail(
            f"actor spawn version {actor.version} не подтверждён для {spec.id}; "
            f"ожидалось {expected}"
        )
    actor_state = _parse_actor_state_details(container.raw, actor)

    relation_registry: XRayRelationRegistry | None = None
    relation_error: str | None = None
    relation_chunk = _chunk_once(chunks, 9, required=False)
    if relation_chunk is not None and strict_registry:
        try:
            relation_registry = parse_relation_registry(relation_chunk.data, spec.id)
        except XRayRelationError as exc:
            # The save remains readable, but a malformed relation prefix must
            # never become an editable goodwill surface.
            relation_registry = None
            relation_error = str(exc)
    if with_inventory:
        objects = _annotate_inventory_placements(
            container.raw,
            objects,
            actor.object_id,
            spec.client_place_offset,
        )
        objects = _annotate_inventory_conditions(container.raw, objects, actor.object_id)
        objects = _annotate_inventory_upgrades(container.raw, objects, actor.object_id)
        objects = _annotate_ammo_objects(container.raw, objects, actor.object_id)

    inventory: tuple[InventoryItem, ...] = ()
    owned_handles: tuple[int, ...] = ()
    unresolved: tuple[int, ...] = ()
    warnings: list[str] = []
    faction_relations: tuple[tuple[int, int], ...] = ()
    faction_relations_editable = False
    if relation_registry is not None:
        try:
            actor_relations = relation_registry.for_character(actor.object_id)
        except XRayRelationError as exc:
            warnings.append(f"X-Ray: actor relation row read-only: {exc}")
        else:
            faction_relations_editable = True
            faction_relations = tuple(
                (entry.community_index, entry.value)
                for entry in actor_relations.communities
            )
    elif relation_chunk is not None and strict_registry:
        detail = f": {relation_error}" if relation_error else ""
        warnings.append(
            f"X-Ray: relation registry не разобран, goodwill только read-only{detail}"
        )
    if with_inventory:
        inventory, owned_handles, unresolved, item_warnings = _inventory_items(
            container.raw, objects, actor.object_id
        )
        warnings.extend(item_warnings)

    parsed = XRaySave(
        data=payload,
        container=container,
        spec=spec,
        actor_version=actor.version,
        actor_id=actor.object_id,
        money=actor_state.money,
        money_offset=actor_state.money_offset,
        player_faction_index=actor_state.player_faction_index,
        player_faction_offset=actor_state.player_faction_offset,
        player_faction_editable=actor_state.player_faction_offset is not None,
        faction_relations=faction_relations,
        relation_registry=relation_registry,
        game_time=game_time,
        time_factor=time_factor,
        normal_time_factor=normal_time_factor,
        level_name=level_name,
        objects=objects,
        inventory=inventory,
        owned_handles=owned_handles,
        unresolved_handles=unresolved,
        warnings=tuple(dict.fromkeys(warnings)),
        faction_relations_editable=faction_relations_editable,
        actor_health=actor_state.health,
        actor_rank=actor_state.rank,
        actor_reputation=actor_state.reputation,
        actor_name=actor_state.character_name,
    )
    if with_inventory:
        parsed = replace(
            parsed,
            inventory=_annotate_inventory_deletion(parsed, parsed.inventory),
        )
    return parsed


def parse_subchunks(raw: bytes) -> tuple[XRayChunk, ...]:
    """Parse nested X-Ray chunks using the same strict framing as the outer stream."""

    # Importing through the module avoids making XRayContainer's public API
    # responsible for the nested stream's error label.
    from .xray_container import parse_chunks

    try:
        return parse_chunks(raw)
    except XRayError as exc:
        raise _fail(str(exc)) from exc


def inspect_xray(
    data: bytes,
    spec: XRayFormatSpec,
    *,
    with_inventory: bool = True,
) -> SaveInfo:
    parsed = parse_xray(data, spec, with_inventory=with_inventory)
    return SaveInfo(
        packed_size=len(data),
        unpacked_size=parsed.container.unpacked_size,
        stored_crc32=0,
        computed_crc32=0,
        crc_ok=True,  # compatibility field; crc_present is the authoritative flag
        sha256=hashlib.sha256(data).hexdigest(),
        money=parsed.money,
        money_anchor_count=1,
        inventory=parsed.inventory,
        owned_handles=parsed.owned_handles,
        grid_cell_count=0,
        orphans=(),
        grid_handle_count=len(parsed.inventory),
        unresolved_handles=parsed.unresolved_handles,
        warnings=parsed.warnings,
        crc_present=False,
        integrity_name="X-Ray LZO/container",
        format_version=parsed.actor_version,
        container_version=parsed.container.version,
        game_time=parsed.game_time,
        time_factor=parsed.time_factor,
        normal_time_factor=parsed.normal_time_factor,
        level_name=parsed.level_name,
        faction_relations=parsed.faction_relations,
        faction_relations_editable=parsed.faction_relations_editable,
        player_faction_index=parsed.player_faction_index,
        player_faction_editable=parsed.player_faction_editable,
        actor_health=parsed.actor_health,
        actor_rank=parsed.actor_rank,
        actor_reputation=parsed.actor_reputation,
        actor_name=parsed.actor_name,
    )


def _validate_source(data: bytes, plan: EditPlan) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != plan.source.sha256:
        raise XRaySaveError(
            "X-Ray save: источник изменился после анализа: "
            f"SHA256 expected={plan.source.sha256} actual={actual}"
        )


def _object_chunk_data(parsed: XRaySave) -> XRayChunk:
    chunk = _chunk_once(parsed.container.chunks, 2)
    assert chunk is not None
    return chunk


def _rebuild_with_object_chunk(parsed: XRaySave, object_data: bytes) -> bytes:
    """Replace only the registry chunk while preserving every other chunk."""

    object_chunk = _object_chunk_data(parsed)
    chunks: list[bytes] = []
    for chunk in parsed.container.chunks:
        payload = object_data if chunk.offset == object_chunk.offset else chunk.data
        chunks.append(struct.pack("<II", chunk.type, len(payload)) + payload)
    raw = b"".join(chunks)
    return parsed.container.build(raw)


def _relation_chunk_data(parsed: XRaySave) -> XRayChunk:
    chunk = _chunk_once(parsed.container.chunks, 9)
    assert chunk is not None
    return chunk


def _rebuild_with_relation_chunk(parsed: XRaySave, relation_data: bytes) -> bytes:
    """Replace only the relation-registry chunk and preserve its tail."""

    relation_chunk = _relation_chunk_data(parsed)
    chunks: list[bytes] = []
    for chunk in parsed.container.chunks:
        payload = relation_data if chunk.offset == relation_chunk.offset else chunk.data
        chunks.append(struct.pack("<II", chunk.type, len(payload)) + payload)
    return parsed.container.build(b"".join(chunks))


def _remove_object_record(parsed: XRaySave, obj: XRayObject) -> bytes:
    object_chunk = _object_chunk_data(parsed)
    data_start = object_chunk.offset + 8
    start = obj.record_offset - data_start
    end = obj.record_end - data_start
    if start < 4 or end > len(object_chunk.data) or start >= end:
        raise _fail(f"object 0x{obj.object_id:04X}: record boundary недействителен")
    count = struct.unpack_from("<I", object_chunk.data, 0)[0]
    if count <= 1:
        raise _fail("OBJECT registry нельзя оставить без actor")
    object_data = struct.pack("<I", count - 1) + object_chunk.data[4:start] + object_chunk.data[end:]
    return _rebuild_with_object_chunk(parsed, object_data)


def _replace_object_record(parsed: XRaySave, obj: XRayObject, record: bytes) -> bytes:
    """Replace one registry record while preserving all neighboring records."""

    object_chunk = _object_chunk_data(parsed)
    data_start = object_chunk.offset + 8
    start = obj.record_offset - data_start
    end = obj.record_end - data_start
    if start < 4 or end > len(object_chunk.data) or start >= end:
        raise _fail(f"object 0x{obj.object_id:04X}: record boundary недействителен")
    if len(record) > 0xFFFF * 2:
        raise _fail(f"object 0x{obj.object_id:04X}: record слишком велик")
    count = struct.unpack_from("<I", object_chunk.data, 0)[0]
    object_data = struct.pack("<I", count) + object_chunk.data[4:start] + record + object_chunk.data[end:]
    return _rebuild_with_object_chunk(parsed, object_data)


def _encode_upgrade_vector(values: tuple[str, ...]) -> bytes:
    if len(values) > _MAX_VECTOR:
        raise _fail(f"upgrades count={len(values)} слишком велик")
    encoded: list[bytes] = []
    for value in values:
        if not value:
            raise _fail("upgrade key must be non-empty")
        if "\x00" in value:
            raise _fail("upgrade key must not contain NUL")
        raw_value = value.encode("utf-8")
        if len(raw_value) > _MAX_STRING:
            raise _fail("upgrade key слишком длинный")
        encoded.append(raw_value + b"\x00")
    return struct.pack("<I", len(values)) + b"".join(encoded)


def _validated_upgrade_catalog(
    spec: XRayFormatSpec,
    upgrade_catalog: UpgradeCatalog | None,
) -> UpgradeCatalog:
    if upgrade_catalog is None:
        raise _fail(
            f"для изменений upgrades нужен официальный upgrade catalog {spec.id!r}"
        )
    if upgrade_catalog.release_id != spec.id:
        raise _fail(
            f"upgrade catalog release {upgrade_catalog.release_id!r} не совпадает "
            f"с save release {spec.id!r}"
        )
    if not upgrade_catalog.upgrades:
        raise _fail(f"upgrade catalog {spec.id!r} не содержит upgrades")
    return upgrade_catalog


def _upgrade_record(
    parsed: XRaySave,
    obj: XRayObject,
    desired: tuple[str, ...],
) -> bytes:
    if obj.upgrades is None or obj.upgrades_offset is None or obj.upgrades_end is None:
        raise _fail(
            f"object 0x{obj.object_id:04X} не имеет подтверждённого m_upgrades vector"
        )
    spawn = parsed.spawn_bytes(obj)
    vector_start = obj.upgrades_offset - obj.spawn_offset
    vector_end = obj.upgrades_end - obj.spawn_offset
    state_size_offset = obj.state_offset - obj.spawn_offset - 2
    if (
        vector_start < 0
        or vector_start >= vector_end
        or vector_end > len(spawn)
        or state_size_offset < 0
        or state_size_offset + 2 > len(spawn)
    ):
        raise _fail(f"object 0x{obj.object_id:04X}: upgrades boundary недействителен")
    encoded = _encode_upgrade_vector(desired)
    rewritten = bytearray(spawn[:vector_start] + encoded + spawn[vector_end:])
    delta = len(encoded) - (vector_end - vector_start)
    state_size = obj.state_size + delta
    if not 2 <= state_size <= 0xFFFF:
        raise _fail(f"object 0x{obj.object_id:04X}: STATE size выходит за u16")
    if len(rewritten) > 0xFFFF:
        raise _fail(f"object 0x{obj.object_id:04X}: SPAWN packet превышает u16 размер")
    struct.pack_into("<H", rewritten, state_size_offset, state_size)
    _parse_spawn(bytes(rewritten), 0)
    update = parsed.update_bytes(obj)
    if len(update) > 0xFFFF:
        raise _fail(f"object 0x{obj.object_id:04X}: UPDATE packet превышает u16 размер")
    return (
        struct.pack("<H", len(rewritten))
        + bytes(rewritten)
        + struct.pack("<H", len(update))
        + update
    )


def _apply_xray_upgrade_edits(
    data: bytes,
    plan: EditPlan,
    spec: XRayFormatSpec,
    upgrade_catalog: UpgradeCatalog | None,
) -> bytes:
    if not plan.upgrades:
        return bytes(data)
    catalog = _validated_upgrade_catalog(spec, upgrade_catalog)
    working = bytes(data)
    for handle, desired in plan.upgrades:
        current = parse_xray(working, spec, with_inventory=True)
        obj = current.object_by_id(handle)
        if obj.parent_id != current.actor_id:
            raise _fail(
                f"object 0x{handle:04X} не принадлежит actor inventory; upgrades read-only"
            )
        if obj.upgrades is None:
            raise _fail(
                f"object 0x{handle:04X} не имеет подтверждённого m_upgrades vector"
            )
        existing = set(obj.upgrades)
        for key in desired:
            if key in existing:
                continue
            definition = catalog.resolve(key)
            if definition is None:
                raise _fail(
                    f"upgrade {key!r} отсутствует в официальном catalog {catalog.release_id!r}"
                )
            if not definition.applies_to(obj.name):
                raise _fail(
                    f"upgrade {key!r} не применим к item {obj.name!r}"
                )
        if desired == obj.upgrades:
            continue
        working = _replace_object_record(
            current,
            obj,
            _upgrade_record(current, obj, desired),
        )
    return working


def _verify_xray_upgrade_edits(
    parsed: XRaySave,
    plan: EditPlan,
    upgrade_catalog: UpgradeCatalog | None,
) -> None:
    if not plan.upgrades:
        return
    _validated_upgrade_catalog(parsed.spec, upgrade_catalog)
    for handle, desired in plan.upgrades:
        checked = parsed.object_by_id(handle)
        if checked.upgrades != desired:
            raise _fail(
                f"round-trip upgrades для 0x{handle:04X} не совпал с {desired!r}"
            )


def _apply_xray_placement_edits(
    data: bytes,
    plan: EditPlan,
    spec: XRayFormatSpec,
) -> bytes:
    """Patch only confirmed ``SInvItemPlace`` values in actor-owned items."""

    working = bytes(data)
    for handle, placement_type, slot_id in plan.placements:
        current = parse_xray(working, spec, with_inventory=True)
        obj = current.object_by_id(handle)
        if obj.parent_id != current.actor_id:
            raise _fail(
                f"object 0x{handle:04X} не принадлежит actor inventory; "
                "placement read-only"
            )
        if obj.placement_offset is None:
            raise _fail(
                f"object 0x{handle:04X} не имеет подтверждённого client-data place; "
                "позиция остаётся read-only"
            )
        if not placement_allowed(
            placement_type,
            slot_id,
            section=obj.name,
            base_slot=obj.placement_base_slot,
            release_id=spec.id,
        ):
            raise _fail(
                f"object 0x{handle:04X} ({obj.name}): игра не кладёт этот предмет в "
                f"{placement_type}{'' if slot_id is None else f' {slot_id}'}; "
                "разрешены рюкзак, пояс для артефактов и собственный слот предмета"
            )
        raw = bytearray(current.container.raw)
        try:
            patch_placement(
                raw,
                obj,
                spec.client_place_offset,
                placement_type,
                slot_id,
            )
        except PlacementCodecError as exc:
            raise _fail(
                f"placement для 0x{handle:04X} не разобран: {exc}"
            ) from exc
        working = current.container.build(bytes(raw))
    return working


def _verify_xray_placement_edits(parsed: XRaySave, plan: EditPlan) -> None:
    """Require the requested decoded place after rebuilding the container."""

    for handle, placement_type, slot_id in plan.placements:
        checked = parsed.object_by_id(handle)
        if checked.placement_type != placement_type:
            raise _fail(
                f"round-trip placement для 0x{handle:04X} не совпал с {placement_type!r}"
            )
        if placement_type == "slot" and checked.placement_slot != slot_id:
            raise _fail(
                f"round-trip slot для 0x{handle:04X} не совпал с {slot_id}"
            )


def _validated_faction_catalog(
    spec: XRayFormatSpec,
    faction_catalog: FactionCatalog | None,
) -> FactionCatalog:
    if faction_catalog is None:
        raise _fail(
            f"для изменений группировок нужен официальный faction catalog {spec.id!r}"
        )
    if faction_catalog.release_id != spec.id:
        raise _fail(
            f"faction catalog release {faction_catalog.release_id!r} не совпадает "
            f"с save release {spec.id!r}"
        )
    if not faction_catalog.factions:
        raise _fail(f"faction catalog {spec.id!r} не содержит communities")
    return faction_catalog


def _faction_numeric_id(
    catalog: FactionCatalog,
    key: str,
) -> int:
    try:
        faction = catalog.resolve(key)
    except LookupError as exc:
        raise _fail(
            f"faction {key!r} отсутствует в официальном catalog {catalog.release_id!r}"
        ) from exc
    if faction.numeric_id is None:
        raise _fail(
            f"faction {key!r} не имеет подтверждённого numeric community id"
        )
    return faction.numeric_id


def _apply_xray_relation_edits(
    data: bytes,
    plan: EditPlan,
    spec: XRayFormatSpec,
    faction_catalog: FactionCatalog | None,
) -> bytes:
    """Patch goodwill values in the actor's serialized relation row."""

    if not plan.faction_relations:
        return bytes(data)
    catalog = _validated_faction_catalog(spec, faction_catalog)
    if catalog.goodwill_min is None or catalog.goodwill_max is None:
        raise _fail(
            f"для {spec.id!r} не подтверждены community goodwill limits; запись запрещена"
        )

    requested = tuple(
        (_faction_numeric_id(catalog, key), goodwill)
        for key, goodwill in plan.faction_relations
    )
    for community_index, goodwill in requested:
        if not catalog.goodwill_min <= goodwill <= catalog.goodwill_max:
            raise _fail(
                f"goodwill для community {community_index} должен быть в диапазоне "
                f"{catalog.goodwill_min}…{catalog.goodwill_max}"
            )

    working = bytes(data)
    for community_index, goodwill in requested:
        current = parse_xray(working, spec, with_inventory=True)
        registry = current.relation_registry
        if registry is None:
            raise _fail("relation registry не разобран; goodwill остаётся read-only")
        try:
            relation_data = patch_relation_registry(
                _relation_chunk_data(current).data,
                registry,
                character_id=current.actor_id,
                community_index=community_index,
                goodwill=goodwill,
            )
        except XRayRelationError as exc:
            raise _fail(str(exc)) from exc
        working = _rebuild_with_relation_chunk(current, relation_data)
    return working


def _verify_xray_relation_edits(
    parsed: XRaySave,
    plan: EditPlan,
    faction_catalog: FactionCatalog | None,
) -> None:
    if not plan.faction_relations:
        return
    catalog = _validated_faction_catalog(parsed.spec, faction_catalog)
    actual = dict(parsed.faction_relations)
    for key, goodwill in plan.faction_relations:
        community_index = _faction_numeric_id(catalog, key)
        if actual.get(community_index) != goodwill:
            raise _fail(
                f"round-trip goodwill для {key!r} не совпал с {goodwill}"
            )


def _apply_xray_player_faction_edit(
    data: bytes,
    plan: EditPlan,
    spec: XRayFormatSpec,
    faction_catalog: FactionCatalog | None,
) -> bytes:
    """Patch the actor community scalar and preserve the rest of actor STATE."""

    if plan.player_faction is None:
        return bytes(data)
    catalog = _validated_faction_catalog(spec, faction_catalog)
    target = _faction_numeric_id(catalog, plan.player_faction)
    if not -0x80000000 <= target <= 0x7FFFFFFF:
        raise _fail(
            f"faction {plan.player_faction!r} numeric community id не помещается в s32"
        )
    parsed = parse_xray(data, spec, with_inventory=True)
    if not parsed.player_faction_editable or parsed.player_faction_offset is None:
        raise _fail(
            "actor community offset не подтверждён для этого X-Ray actor STATE; "
            "принадлежность остаётся read-only"
        )
    raw = bytearray(parsed.container.raw)
    struct.pack_into("<i", raw, parsed.player_faction_offset, target)
    return parsed.container.build(bytes(raw))


def _verify_xray_player_faction_edit(
    parsed: XRaySave,
    plan: EditPlan,
    faction_catalog: FactionCatalog | None,
) -> None:
    if plan.player_faction is None:
        return
    catalog = _validated_faction_catalog(parsed.spec, faction_catalog)
    expected = _faction_numeric_id(catalog, plan.player_faction)
    if parsed.player_faction_index != expected:
        raise _fail(
            f"round-trip player community для {plan.player_faction!r} не совпал "
            f"с {expected}"
        )


def _append_object_record(parsed: XRaySave, record: bytes) -> bytes:
    object_chunk = _object_chunk_data(parsed)
    count = struct.unpack_from("<I", object_chunk.data, 0)[0]
    if count >= _MAX_OBJECTS:
        raise _fail("OBJECT registry достиг максимального размера")
    object_data = struct.pack("<I", count + 1) + object_chunk.data[4:] + record
    return _rebuild_with_object_chunk(parsed, object_data)


def _patch_spawn_identity(
    packet: bytes,
    *,
    name: str,
    object_id: int,
    parent_id: int,
) -> bytes:
    """Patch identity fields after parsing their serialized field sequence."""

    if "\x00" in name:
        raise _fail("serialized item key содержит NUL")
    if not 0 <= object_id <= 0xFFFF or not 0 <= parent_id <= 0xFFFF:
        raise _fail("object identity выходит за u16")
    original = bytes(packet)
    reader = _Reader(original, label="SPAWN identity")
    if reader.u16() != _M_SPAWN:
        raise _fail("SPAWN identity не начинается с M_SPAWN")
    name_start = reader.pos
    reader.zstring()
    name_end = reader.pos
    reader.zstring()
    reader.u8()
    reader.u8()
    for _ in range(6):
        reader.f32()
    reader.u16()  # respawn time
    object_id_offset = reader.pos
    reader.u16()
    parent_id_offset = reader.pos
    reader.u16()

    replacement = name.encode("utf-8") + b"\x00"
    rewritten = bytearray(original[:name_start] + replacement + original[name_end:])
    delta = len(replacement) - (name_end - name_start)
    struct.pack_into("<H", rewritten, object_id_offset + delta, object_id)
    struct.pack_into("<H", rewritten, parent_id_offset + delta, parent_id)
    _parse_spawn(bytes(rewritten), 0)
    return bytes(rewritten)


def _allocate_object_id(objects: tuple[XRayObject, ...]) -> int:
    used = {obj.object_id for obj in objects}
    highest = max(used, default=0)
    for candidate in range(highest + 1, 0xFFFF):
        if candidate not in used:
            return candidate
    for candidate in range(1, highest + 1):
        if candidate not in used:
            return candidate
    raise _fail("не осталось свободных object id")


def _clone_ammo_record(
    parsed: XRaySave,
    prototype: XRayObject,
    *,
    item_key: str,
    object_id: int,
    actor_id: int,
    quantity: int,
) -> bytes:
    if prototype.count is None or prototype.ammo_state_offset is None:
        raise _fail(f"prototype {prototype.name!r} не имеет подтверждённого ammo STATE")
    if prototype.update_count is None or prototype.ammo_update_offset is None:
        raise _fail(f"prototype {prototype.name!r} не имеет подтверждённого ammo UPDATE")

    spawn = _patch_spawn_identity(
        parsed.spawn_bytes(prototype),
        name=item_key,
        object_id=object_id,
        parent_id=actor_id,
    )
    spawned = _parse_spawn(spawn, 0)
    state_offset, _ = _parse_ammo_state_window(
        spawn,
        state_offset=spawned.state_start,
        state_end=spawned.state_end,
        version=spawned.version,
        label=f"{item_key} STATE",
    )
    spawn_mut = bytearray(spawn)
    struct.pack_into("<H", spawn_mut, state_offset, quantity)

    update = bytearray(parsed.update_bytes(prototype))
    if len(update) < 4 or struct.unpack_from("<H", update, 0)[0] != _M_UPDATE:
        raise _fail(f"prototype {prototype.name!r}: UPDATE boundary недействителен")
    struct.pack_into("<H", update, len(update) - 2, quantity)
    if len(spawn_mut) > 0xFFFF or len(update) > 0xFFFF:
        raise _fail("новая object record packet превышает u16 размер")
    return (
        struct.pack("<H", len(spawn_mut))
        + bytes(spawn_mut)
        + struct.pack("<H", len(update))
        + bytes(update)
    )


def _clone_registry_record(
    parsed: XRaySave,
    prototype: XRayObject,
    *,
    item_key: str,
    object_id: int,
    actor_id: int,
    family: str,
    quantity: int,
) -> bytes:
    """Clone one exact STATE/UPDATE serializer family from the registry."""

    if family == "ammo":
        return _clone_ammo_record(
            parsed,
            prototype,
            item_key=item_key,
            object_id=object_id,
            actor_id=actor_id,
            quantity=quantity,
        )
    if family not in {
        "base",
        "detector",
        "outfit",
        "pda",
        "document",
        "torch",
        "weapon",
        "weapon_magazined",
        "weapon_shotgun",
        "weapon_wgl",
    }:
        raise _fail(f"serializer family {family!r} не подтверждён")

    spawn = _patch_spawn_identity(
        parsed.spawn_bytes(prototype),
        name=item_key,
        object_id=object_id,
        parent_id=actor_id,
    )
    update = parsed.update_bytes(prototype)
    if len(spawn) > 0xFFFF or len(update) > 0xFFFF:
        raise _fail("новая object record packet превышает u16 размер")
    return (
        struct.pack("<H", len(spawn))
        + spawn
        + struct.pack("<H", len(update))
        + update
    )


def _find_registry_template(
    parsed: XRaySave,
    catalog: ItemCatalog,
    *,
    actor_id: int,
    family: str,
) -> XRayObject | None:
    """Prefer an actor-owned object, then a known registry object."""

    candidates = tuple(
        obj for obj in parsed.objects if obj.object_id != parsed.actor_id
    )
    ordered = tuple(
        obj for obj in candidates if obj.parent_id == actor_id
    ) + tuple(obj for obj in candidates if obj.parent_id != actor_id)
    for obj in ordered:
        if _object_serialization_family(obj, catalog) == family:
            return obj
    return None


def _added_items_match(
    before: XRaySave,
    after: XRaySave,
    plan: EditPlan,
    catalog: ItemCatalog,
) -> bool:
    before_handles = {item.handle for item in before.inventory}
    for item_key, quantity, _destination in plan.adds:
        definition = catalog.resolve(item_key)
        if definition is None:
            return False
        family = _definition_serialization_family(definition)
        added = tuple(
            item
            for item in after.inventory
            if item.handle not in before_handles and item.type_key == item_key
        )
        if family == "ammo":
            if not any(item.count == quantity for item in added):
                return False
        elif len(added) != quantity:
            return False
    return True


def _apply_xray_structural_edits(
    data: bytes,
    plan: EditPlan,
    spec: XRayFormatSpec,
    catalog: ItemCatalog | None,
) -> bytes:
    working = bytes(data)

    for handle, deep in plan.detach:
        current = parse_xray(working, spec, with_inventory=True)
        if not deep:
            raise XRaySaveError(
                "X-Ray save: только deep detach подтверждён для registry object"
            )
        analysis = analyze_xray_delete(current, handle)
        if not analysis.allowed:
            raise XRaySaveError(
                f"X-Ray save: delete 0x{handle:04X} отказан: {analysis.message}"
            )
        obj = current.object_by_id(handle)
        working = _remove_object_record(current, obj)

    for item_key, quantity, destination in plan.adds:
        request = XRayItemAdd(None, item_key, quantity, destination)
        if catalog is None:
            raise XRaySaveError(
                f"X-Ray save: для добавления {request.item_key!r} нужен официальный catalog"
            )
        if catalog.release_id != spec.id:
            raise XRaySaveError(
                f"X-Ray save: catalog {catalog.release_id!r} не относится к {spec.id!r}"
            )
        definition = catalog.resolve(request.item_key)
        if definition is None:
            raise XRaySaveError(
                f"X-Ray save: item key {request.item_key!r} отсутствует в catalog"
            )
        family = _definition_serialization_family(definition)
        if family not in {
            "ammo",
            "base",
            "detector",
            "outfit",
            "pda",
            "document",
            "torch",
            "weapon",
            "weapon_magazined",
            "weapon_shotgun",
            "weapon_wgl",
        }:
            raise XRaySaveError(
                f"X-Ray save: item {request.item_key!r} имеет неподтверждённое serializer family"
            )
        if family == "ammo" and definition.max_stack is not None and request.quantity > definition.max_stack:
            raise XRaySaveError(
                f"X-Ray save: quantity {request.quantity} превышает max_stack {definition.max_stack}"
            )

        current = parse_xray(working, spec, with_inventory=True)
        prototype = _find_registry_template(
            current,
            catalog,
            actor_id=current.actor_id,
            family=family,
        )
        if prototype is None:
            raise XRaySaveError(
                f"X-Ray save: не найден существующий registry template для family {family!r}"
            )
        copies = 1 if family == "ammo" else request.quantity
        for _copy_index in range(copies):
            current = parse_xray(working, spec, with_inventory=True)
            # A new record receives one fresh u16 handle; reparse after every
            # append keeps offsets exact when the registry grows.
            new_id = _allocate_object_id(current.objects)
            record = _clone_registry_record(
                current,
                prototype,
                item_key=request.item_key,
                object_id=new_id,
                actor_id=current.actor_id,
                family=family,
                quantity=request.quantity,
            )
            working = _append_object_record(current, record)

    return working


def prepare_xray(
    data: bytes,
    plan: EditPlan,
    spec: XRayFormatSpec,
    *,
    catalog: ItemCatalog | None = None,
    faction_catalog: FactionCatalog | None = None,
    upgrade_catalog: UpgradeCatalog | None = None,
) -> PreparedEdit:
    """Prepare proven X-Ray edits and verify their structural round-trip."""

    payload = bytes(data)
    _validate_source(payload, plan)
    if plan.moves:
        raise XRaySaveError("X-Ray save: move для оригинальной трилогии пока read-only")
    if plan.attach:
        raise XRaySaveError("X-Ray save: attach требует prototype/registry writer и запрещён")
    if plan.raw:
        raise XRaySaveError("X-Ray save: raw patch запрещён для сохранения неизвестных полей")
    if plan.money is not None and not 0 <= plan.money <= 2_000_000_000:
        raise XRaySaveError("X-Ray save: деньги должны быть в диапазоне 0…2 000 000 000")

    parsed = parse_xray(payload, spec, with_inventory=True)
    before_structural = parsed
    working_data = payload
    if plan.faction_relations:
        working_data = _apply_xray_relation_edits(
            working_data,
            plan,
            spec,
            faction_catalog,
        )
    if plan.player_faction is not None:
        working_data = _apply_xray_player_faction_edit(
            working_data,
            plan,
            spec,
            faction_catalog,
        )
    if plan.detach or plan.adds:
        working_data = _apply_xray_structural_edits(
            working_data,
            plan,
            spec,
            catalog,
        )
    if plan.upgrades:
        working_data = _apply_xray_upgrade_edits(
            working_data,
            plan,
            spec,
            upgrade_catalog,
        )
    if plan.placements:
        working_data = _apply_xray_placement_edits(working_data, plan, spec)
    if working_data != payload:
        parsed = parse_xray(working_data, spec, with_inventory=True)

    if (
        plan.money is None
        and not plan.stacks
        and not plan.durability
        and not plan.faction_relations
        and plan.player_faction is None
        and not plan.upgrades
        and not plan.placements
    ):
        _verify_xray_relation_edits(parsed, plan, faction_catalog)
        _verify_xray_player_faction_edit(parsed, plan, faction_catalog)
        _verify_xray_upgrade_edits(parsed, plan, upgrade_catalog)
        _verify_xray_placement_edits(parsed, plan)
        for handle, _ in plan.detach:
            if any(item.handle == handle for item in parsed.inventory):
                raise XRaySaveError(
                    f"X-Ray save: detach round-trip оставил object 0x{handle:04X}"
                )
        if plan.adds and catalog is not None and not _added_items_match(
            before_structural, parsed, plan, catalog
        ):
            raise XRaySaveError("X-Ray save: add round-trip не создал ожидаемые registry items")
        output = bytes(working_data)
        return PreparedEdit(plan=plan, data=output, output_sha256=hashlib.sha256(output).hexdigest())

    raw = bytearray(parsed.container.raw)
    if plan.money is not None:
        struct.pack_into("<I", raw, parsed.money_offset, plan.money)

    requested = dict(plan.stacks)
    for handle, count in requested.items():
        if not 1 <= count <= _MAX_AMMO_COUNT:
            raise XRaySaveError(
                f"X-Ray save: ammo count для 0x{handle:04X} должен быть 1…65535"
            )
        obj = parsed.object_by_id(handle)
        if obj.ammo_state_offset is None or obj.ammo_update_offset is None or obj.count is None:
            raise XRaySaveError(
                f"X-Ray save: object 0x{handle:04X} не является подтверждённым ammo stack"
            )
        struct.pack_into("<H", raw, obj.ammo_state_offset, count)
        struct.pack_into("<H", raw, obj.ammo_update_offset, count)

    requested_durability = dict(plan.durability)
    for handle, condition in requested_durability.items():
        obj = parsed.object_by_id(handle)
        if (
            obj.condition is None
            or obj.condition_family not in CONDITION_FAMILIES
            or obj.condition_offset is None
        ):
            raise XRaySaveError(
                f"X-Ray save: object 0x{handle:04X} не является подтверждённым item condition"
            )
        try:
            patch_condition(raw, obj, obj.condition_family, condition)
        except ConditionCodecError as exc:
            raise XRaySaveError(
                f"X-Ray save: condition для 0x{handle:04X} не разобран: {exc}"
            ) from exc

    rebuilt = parsed.container.build(bytes(raw))
    after = parse_xray(rebuilt, spec, with_inventory=True)
    _verify_xray_relation_edits(after, plan, faction_catalog)
    _verify_xray_player_faction_edit(after, plan, faction_catalog)
    _verify_xray_upgrade_edits(after, plan, upgrade_catalog)
    _verify_xray_placement_edits(after, plan)
    if plan.money is not None and after.money != plan.money:
        raise XRaySaveError(
            f"X-Ray save: round-trip деньги={after.money}, ожидалось {plan.money}"
        )
    for handle, count in requested.items():
        checked = after.object_by_id(handle)
        if checked.count != count or checked.update_count != count:
            raise XRaySaveError(
                f"X-Ray save: round-trip ammo 0x{handle:04X} не совпал с {count}"
            )
    for handle, condition in requested_durability.items():
        checked = after.object_by_id(handle)
        if checked.condition is None or not math.isclose(
            checked.condition, condition, rel_tol=0.0, abs_tol=1e-6
        ):
            raise XRaySaveError(
                f"X-Ray save: round-trip condition 0x{handle:04X} не совпал с {condition}"
            )
        if checked.update_condition_offset is not None:
            expected = min(255, max(0, math.floor(condition * 255.0 + 0.5)))
            if after.container.raw[checked.update_condition_offset] != expected:
                raise XRaySaveError(
                    f"X-Ray save: round-trip UPDATE condition 0x{handle:04X} не совпал"
                )
    for handle, _ in plan.detach:
        if any(item.handle == handle for item in after.inventory):
            raise XRaySaveError(
                f"X-Ray save: detach round-trip оставил object 0x{handle:04X}"
            )
    if plan.adds and catalog is not None and not _added_items_match(
        before_structural, after, plan, catalog
    ):
        raise XRaySaveError("X-Ray save: add round-trip не создал ожидаемые registry items")
    output = bytes(rebuilt)
    return PreparedEdit(
        plan=plan,
        data=output,
        output_sha256=hashlib.sha256(output).hexdigest(),
    )


__all__ = [
    "COP_FORMAT",
    "CS_FORMAT",
    "SOC_FORMAT",
    "XRAY_EE_FORMATS",
    "XRAY_FORMATS",
    "XRayFormatSpec",
    "XRayItemAdd",
    "XRayObject",
    "XRaySave",
    "XRaySaveError",
    "catalog_from_save_inventory",
    "inspect_xray",
    "parse_subchunks",
    "parse_xray",
    "prepare_xray",
]
