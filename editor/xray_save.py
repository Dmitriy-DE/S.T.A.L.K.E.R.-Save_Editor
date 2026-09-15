"""Read and safely patch the original trilogy's X-Ray save objects.

The original games do not use the S.T.A.L.K.E.R. 2 GVAS/CRC container.  They
store a versioned chunk stream in a raw LZO1X payload.  This module keeps the
format-specific part small and explicit: it parses the common object envelope,
the actor money field, and the ``CSE_ALifeItemAmmo`` count fields documented in
the public X-Ray source.  Unknown object state remains untouched.

There is intentionally no item allocator, prototype catalogue, or structural
object writer here.  Adding a new item safely requires game configuration and
registry semantics that are not present in a save file alone.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass, replace

from save_format import InventoryItem, SaveInfo

from .catalog import ItemCatalog
from .models import EditPlan, PreparedEdit
from .xray_container import XRayChunk, XRayContainer, XRayError

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


SOC_FORMAT = XRayFormatSpec(
    id="stalker-soc",
    title="S.T.A.L.K.E.R.: Shadow of Chernobyl",
    extension=".sav",
    outer_versions=frozenset({3}),
    actor_versions=frozenset({118}),
)
CS_FORMAT = XRayFormatSpec(
    id="stalker-cs",
    title="S.T.A.L.K.E.R.: Clear Sky",
    extension=".sav",
    outer_versions=frozenset({5}),
    actor_versions=frozenset({122, 123, 124}),
)
COP_FORMAT = XRayFormatSpec(
    id="stalker-cop",
    title="S.T.A.L.K.E.R.: Call of Pripyat",
    extension=".scop",
    outer_versions=frozenset({6}),
    actor_versions=frozenset({128}),
)
XRAY_FORMATS = (SOC_FORMAT, CS_FORMAT, COP_FORMAT)


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
    state_size: int
    state_offset: int
    state_end: int
    update_offset: int
    update_end: int
    update_size: int
    count: int | None = None
    update_count: int | None = None
    ammo_state_offset: int | None = None
    ammo_update_offset: int | None = None
    unknown_fields: tuple[str, ...] = (
        "prototype",
        "durability",
        "upgrades",
        "inventory position",
    )


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
    game_time: int | None
    time_factor: float | None
    normal_time_factor: float | None
    level_name: str | None
    objects: tuple[XRayObject, ...]
    inventory: tuple[InventoryItem, ...]
    owned_handles: tuple[int, ...]
    unresolved_handles: tuple[int, ...]
    warnings: tuple[str, ...]

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


def _parse_actor_state(raw: bytes, obj: XRayObject) -> tuple[int, int]:
    reader = _Reader(raw[obj.state_offset : obj.state_end], label="actor STATE")
    version = obj.version

    _read_dynamic_visual_state(reader, version)
    reader.u8()  # team
    reader.u8()  # squad
    reader.u8()  # group
    if version > 18:
        reader.f32()  # health
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
    return money_offset, money


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
    if version > 70:
        client_size = reader.u16() if version > 93 else reader.u8()
        if client_size > 256 * 1024:
            raise _fail(f"объект {name!r}: client data слишком велик")
        reader.bytes(client_size)
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
    if lowered.startswith(("outfit_", "scientific_", "helm_", "armor_")):
        return 1, "Броня/экипировка"
    if lowered.startswith(("af_", "artifact_")):
        return 2, "Артефакт"
    if lowered.startswith(("grenade", "rgd", "f1_")):
        return 7, "Гранаты/стак"
    if lowered.startswith(
        ("medkit", "bandage", "antirad", "drug_", "food_", "bread", "kolbasa", "vodka", "energy")
    ):
        return 4, "Расходник"
    return 8, "Разное"


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
                position_label="в инвентаре",
                size_label="неизвестно",
                count_max=_MAX_AMMO_COUNT,
            )
        )
    items.sort(key=lambda item: item.handle)
    warnings.append(
        "X-Ray: названия и категории предметов показаны по serialized section key; "
        "перевод, вес, размер и точная UI-сетка не извлечены"
    )
    return tuple(items), tuple(obj.object_id for obj in children), tuple(unresolved), tuple(warnings)


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
    if alife_version != container.version:
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
    try:
        money_offset, money = _parse_actor_state(container.raw, actor)
    except XRaySaveError:
        raise
    if with_inventory:
        objects = _annotate_ammo_objects(container.raw, objects, actor.object_id)

    inventory: tuple[InventoryItem, ...] = ()
    owned_handles: tuple[int, ...] = ()
    unresolved: tuple[int, ...] = ()
    warnings: list[str] = []
    if with_inventory:
        inventory, owned_handles, unresolved, item_warnings = _inventory_items(
            container.raw, objects, actor.object_id
        )
        warnings.extend(item_warnings)

    return XRaySave(
        data=payload,
        container=container,
        spec=spec,
        actor_version=actor.version,
        actor_id=actor.object_id,
        money=money,
        money_offset=money_offset,
        game_time=game_time,
        time_factor=time_factor,
        normal_time_factor=normal_time_factor,
        level_name=level_name,
        objects=objects,
        inventory=inventory,
        owned_handles=owned_handles,
        unresolved_handles=unresolved,
        warnings=tuple(dict.fromkeys(warnings)),
    )


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
        obj = current.object_by_id(handle)
        if obj.parent_id != current.actor_id:
            raise XRaySaveError(
                f"X-Ray save: object 0x{handle:04X} не принадлежит actor inventory"
            )
        if not obj.name.lower().startswith("ammo_"):
            raise XRaySaveError(
                f"X-Ray save: удаление {obj.name!r} пока подтверждено только для ammo"
            )
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
        if definition.category != "ammo" or definition.prototype is None:
            raise XRaySaveError(
                f"X-Ray save: item {request.item_key!r} не имеет подтверждённого ammo prototype"
            )
        if definition.max_stack is not None and request.quantity > definition.max_stack:
            raise XRaySaveError(
                f"X-Ray save: quantity {request.quantity} превышает max_stack {definition.max_stack}"
            )

        current = parse_xray(working, spec, with_inventory=True)
        prototype = next(
            (
                obj
                for obj in current.objects
                if obj.parent_id == current.actor_id
                and obj.name.lower().startswith("ammo_")
                and obj.count is not None
                and obj.update_count is not None
            ),
            None,
        )
        if prototype is None:
            raise XRaySaveError(
                "X-Ray save: не найден существующий подтверждённый ammo object для clone"
            )
        new_id = _allocate_object_id(current.objects)
        record = _clone_ammo_record(
            current,
            prototype,
            item_key=request.item_key,
            object_id=new_id,
            actor_id=current.actor_id,
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
    working_data = payload
    if plan.detach or plan.adds:
        working_data = _apply_xray_structural_edits(
            payload,
            plan,
            spec,
            catalog,
        )
        parsed = parse_xray(working_data, spec, with_inventory=True)

    if plan.money is None and not plan.stacks:
        for handle, _ in plan.detach:
            if any(item.handle == handle for item in parsed.inventory):
                raise XRaySaveError(
                    f"X-Ray save: detach round-trip оставил object 0x{handle:04X}"
                )
        for item_key, quantity, _ in plan.adds:
            if not any(
                item.type_key == item_key and item.count == quantity
                for item in parsed.inventory
            ):
                raise XRaySaveError(
                    f"X-Ray save: add round-trip не создал {item_key!r} x{quantity}"
                )
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

    rebuilt = parsed.container.build(bytes(raw))
    after = parse_xray(rebuilt, spec, with_inventory=True)
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
    for handle, _ in plan.detach:
        if any(item.handle == handle for item in after.inventory):
            raise XRaySaveError(
                f"X-Ray save: detach round-trip оставил object 0x{handle:04X}"
            )
    for item_key, quantity, _ in plan.adds:
        if not any(
            item.type_key == item_key and item.count == quantity
            for item in after.inventory
        ):
            raise XRaySaveError(
                f"X-Ray save: add round-trip не создал {item_key!r} x{quantity}"
            )
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
    "XRAY_FORMATS",
    "XRayFormatSpec",
    "XRayItemAdd",
    "XRayObject",
    "XRaySave",
    "XRaySaveError",
    "inspect_xray",
    "parse_subchunks",
    "parse_xray",
    "prepare_xray",
]
