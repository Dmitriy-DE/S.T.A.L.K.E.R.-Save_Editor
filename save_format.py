from __future__ import annotations

import hashlib
import math
import struct
import zlib
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from editor.codec import CodecError
from editor.codec import compress as codec_compress
from editor.codec import decompress as codec_decompress
from editor.kraken_blocks import (
    CompactRebuildResult,
    KrakenBlocksError,
    RebuildMode,
    compact_rebuild_stream,
    parse_kraken_stream,
)
from editor.s2_item_state import (
    S2_EQUIPMENT_KIND_CODES,
    S2ConditionAnchor,
    S2NameTables,
    S2WeaponConditionAnchor,
    has_s2_equipment_shape,
    patch_s2_armor_condition,
    patch_s2_weapon_condition,
    read_s2_armor_condition,
    read_s2_armor_upgrades,
    read_s2_weapon_condition,
    s2_name_for_key,
)

BLOCK_SIZE = 0x40000
UNCOMPRESSED_BLOCK_HEADER = b"\xCC\x06"
GRID_RECORD_SIZE = 8
GRID_WIDTH = 8
KNOWN_KIND_CODES = frozenset({0, 1, 2, 4, 5, 6, 7, 8, 10, 11})
# Actor-owned S2 records kept outside the backpack grid that are not worn
# weapons/armour/artifacts: detectors (6), blueprints/quest data (8),
# night vision (10) and binoculars (11).  Listed read-only.
S2_CARRIED_KIND_CODES = frozenset({6, 8, 10, 11})
EDITABLE_STACK_KIND_CODES = frozenset({4, 5, 7, 8})
SINGLE_STACK_KIND_CODES = frozenset({4, 5, 7})

# Confirmed in the user's real saves. This is a campaign/player structure anchor,
# not a universal GSC guarantee; all mutating operations fail closed if it stops
# being unique.
MONEY_ANCHOR = bytes.fromhex(
    "0038010000000110cacfa848c8952149b51b9444000000000600000000060000"
)

# The GUID inside MONEY_ANCHOR.  Launch builds (v1.0.x, late 2024) keep it
# once but with a different surrounding layout, so the anchor is absent.
WALLET_FIELD_ID = MONEY_ANCHOR[8:20]

# Object record fields confirmed on several nearby saves / UI screenshots.
OBJ_POS_X_OFFSET = 11
OBJ_POS_Y_OFFSET = 13
STACK_MARKER_OFFSET = 18
STACK_COUNT_OFFSET = 19
STACK_WEIGHT_OFFSET = 24
STACK_KIND_OFFSET = 31


class SaveError(RuntimeError):
    pass


@dataclass(frozen=True)
class GridCell:
    handle: int
    x: int
    y: int


@dataclass(frozen=True)
class InventoryLayout:
    anchor_offset: int
    money_offset: int
    owned_flag_offset: int
    owned_count_offset: int
    owned_handles_offset: int
    owned_handles: tuple[int, ...]
    grid_count_offset: int
    grid_offset: int
    grid_cells: tuple[GridCell, ...]
    grid_end_offset: int
    declared_grid_count: int = 0
    grid_handle_count: int = 0
    unresolved_handles: tuple[int, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class InventoryItem:
    handle: int
    x: int | None
    y: int | None
    width: int | None
    height: int | None
    cells: tuple[tuple[int, int], ...]
    count: int | None
    total_weight: float | None
    unit_weight: float | None
    kind_code: int
    category: str
    record_offset: int
    record_end_guess: int
    fingerprint: str
    type_key: str
    editable_count: bool
    display_name: str | None = None
    position_label: str | None = None
    size_label: str | None = None
    count_max: int = 1_000_000
    condition: float | None = None
    condition_editable: bool = False
    storage: Literal["equipped", "inventory"] | None = None
    modules: tuple[str, ...] | None = None
    upgrades: tuple[str, ...] | None = None
    upgrades_editable: bool = False
    placement_type: Literal["slot", "belt", "ruck"] | None = None
    placement_slot: int | None = None
    placement_base_slot: int | None = None
    placement_editable: bool = False
    remove_editable: bool = False
    remove_reason: str | None = None
    # Name-table/catalog records never become InventoryItem rows. This
    # provenance identifies which owned storage observation produced a row.
    observation_source: Literal["actor_inventory", "grid", "equipped", "carried"] = (
        "actor_inventory"
    )

    @property
    def handle_hex(self) -> str:
        return f"0x{self.handle:08X}"

    @property
    def position(self) -> str:
        if self.position_label is not None or self.x is None or self.y is None:
            return self.position_label or "неизвестно"
        return f"{self.x},{self.y}"

    @property
    def size_text(self) -> str:
        if self.size_label is not None or self.width is None or self.height is None:
            return self.size_label or "неизвестно"
        return f"{self.width}×{self.height}"


@dataclass(frozen=True)
class OrphanItem:
    handle: int
    record_offset: int
    x: int
    y: int
    count: int
    total_weight: float
    kind_code: int
    category: str
    type_key: str

    @property
    def handle_hex(self) -> str:
        return f"0x{self.handle:08X}"


@dataclass(frozen=True)
class RawPatch:
    offset: int
    kind: str
    value: str
    note: str = ""


@dataclass
class SaveInfo:
    packed_size: int
    unpacked_size: int
    stored_crc32: int
    computed_crc32: int
    crc_ok: bool
    sha256: str
    money: int | None
    money_anchor_count: int
    inventory: tuple[InventoryItem, ...] = ()
    owned_handles: tuple[int, ...] = ()
    grid_cell_count: int = 0
    orphans: tuple[OrphanItem, ...] = ()
    grid_handle_count: int = 0
    unresolved_handles: tuple[int, ...] = ()
    warnings: tuple[str, ...] = ()
    crc_present: bool = True
    integrity_name: str = "CRC-32"
    format_version: int | None = None
    game_time: int | None = None
    time_factor: float | None = None
    normal_time_factor: float | None = None
    level_name: str | None = None
    container_version: int | None = None
    faction_relations: tuple[tuple[int, int], ...] = ()
    faction_relations_editable: bool = False
    player_faction_index: int | None = None
    player_faction_editable: bool = False
    # Read-only X-Ray actor facts (never written).
    actor_health: float | None = None
    actor_rank: int | None = None
    actor_reputation: int | None = None
    actor_name: str | None = None


@dataclass(frozen=True)
class PatchResult:
    data: bytes
    old_money: int | None
    new_money: int | None
    changed_stacks: tuple[tuple[int, int, int], ...]
    moved_items: tuple[tuple[int, int, int, int, int], ...]  # h, ox, oy, nx, ny
    detached_items: tuple[tuple[int, bool], ...]  # h, deep-remove-owned-handle
    attached_items: tuple[tuple[int, int, int, int, int], ...]  # h,x,y,w,h
    raw_patches: tuple[RawPatch, ...]
    rebuild_mode: RebuildMode = "full-fallback"
    preserved_blocks: int = 0
    rebuilt_blocks: int = 0
    rebuild_reason: str = ""


def validate_crc(data: bytes) -> tuple[int, int, bool]:
    if len(data) < 8:
        raise SaveError("Файл слишком маленький и не похож на STALKER 2 .sav")
    stored = struct.unpack_from("<I", data, len(data) - 4)[0]
    computed = zlib.crc32(data[:-4]) & 0xFFFFFFFF
    return stored, computed, stored == computed


def decompress_save(data: bytes) -> bytes:
    if len(data) < 8:
        raise SaveError("Файл слишком маленький")
    unpacked_size = struct.unpack_from("<I", data, 0)[0]
    if unpacked_size <= 0 or unpacked_size > 512 * 1024 * 1024:
        raise SaveError(f"Подозрительный распакованный размер: {unpacked_size}")
    try:
        raw = codec_decompress(data[4:-4], unpacked_size)
    except CodecError as exc:
        raise SaveError(f"Kraken/Oodle распаковка не удалась: {exc}") from exc
    if len(raw) != unpacked_size:
        raise SaveError(
            f"Неверный размер после распаковки: {len(raw)} вместо {unpacked_size}"
        )
    return bytes(raw)


def _find_all(raw: bytes | bytearray, needle: bytes) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        i = raw.find(needle, start)
        if i < 0:
            return out
        out.append(i)
        start = i + 1


def locate_money(raw: bytes | bytearray) -> tuple[int, int]:
    positions = _find_all(raw, MONEY_ANCHOR)
    if len(positions) != 1:
        raise SaveError(
            f"Сигнатура кошелька найдена {len(positions)} раз(а), ожидалось ровно 1. "
            "Автоправка остановлена, чтобы не повредить сейв."
        )
    money_off = positions[0] + len(MONEY_ANCHOR)
    if money_off + 4 > len(raw):
        raise SaveError("Поле денег выходит за границы payload")
    money = struct.unpack_from("<I", raw, money_off)[0]
    return money_off, money


def _category_name(kind: int) -> str:
    return {
        0: "Оружие",
        1: "Броня/экипировка",
        2: "Артефакт",
        4: "Расходник",
        5: "Патроны",
        6: "Детектор",
        7: "Гранаты",
        8: "Разное",
        10: "ПНВ",
        11: "Бинокль",
    }.get(kind, f"Тип {kind}")


def _s2_category_name(kind: int, display_name: str | None) -> str:
    """Use save-local names instead of treating a serialization kind as class."""

    normalized = (display_name or "").strip().casefold()
    if normalized.startswith(
        ("nvg_", "binocular", "binoculars", "пнв", "бинокль", "бинокл")
    ):
        return "Устройство"
    if "_upgrade_" in normalized or "_attachment_" in normalized:
        return "Модуль/улучшение"
    if _s2_armor_name(display_name) or normalized.endswith("_helmet"):
        return "Броня/экипировка"
    if "_armor_" in normalized or "_helmet_" in normalized:
        return "Разное"
    if normalized.startswith("gunbucket_"):
        return "Разное"
    return _category_name(kind)


def _s2_armor_name(display_name: str | None) -> bool:
    """Return whether a save-local S2 name has the exact observed armor suffix."""

    normalized = (display_name or "").strip().replace(" ", "_").casefold()
    return normalized.endswith("_armor")


def locate_inventory_layout(raw: bytes) -> InventoryLayout:
    """Parse the confirmed player-inventory arrays near the wallet anchor.

    Confirmed layout after u32 money:
      u32 owned_flag (observed == 1)
      u16 owned_handle_count
      u32 owned_handles[count]
      u16 grid_cell_count
      GridCell[grid_cell_count] where GridCell = <IHH>

    This supersedes the old hardcoded +0x100 grid offset: the offset happens to
    match one save, but the count-derived parser survives list size changes.
    """
    positions = _find_all(raw, MONEY_ANCHOR)
    if len(positions) != 1:
        raise SaveError(
            f"Нельзя найти inventory layout: anchor кошелька встречается {len(positions)} раз(а)"
        )
    anchor = positions[0]
    money_off = anchor + len(MONEY_ANCHOR)
    flag_off = money_off + 4
    count_off = money_off + 8
    if count_off + 2 > len(raw):
        raise SaveError("Inventory owned-handle header выходит за payload")
    owned_count = struct.unpack_from("<H", raw, count_off)[0]
    if not (0 <= owned_count <= 4096):
        raise SaveError(f"Подозрительный owned handle count: {owned_count}")
    handles_off = count_off + 2
    handles_end = handles_off + owned_count * 4
    if handles_end + 2 > len(raw):
        raise SaveError("Owned handle array выходит за payload")
    owned = struct.unpack_from(f"<{owned_count}I", raw, handles_off) if owned_count else ()
    if owned and sum(1 for h in owned if (h >> 24) == 0x30) < max(4, owned_count // 2):
        raise SaveError("Owned handle array не похож на player object handles")

    grid_count_off = handles_end
    grid_count = struct.unpack_from("<H", raw, grid_count_off)[0]
    if not (0 <= grid_count <= 8192):
        raise SaveError(f"Подозрительный grid cell count: {grid_count}")
    grid_off = grid_count_off + 2
    grid_end = grid_off + grid_count * GRID_RECORD_SIZE
    if grid_end > len(raw):
        raise SaveError("Inventory grid выходит за payload")

    cells: list[GridCell] = []
    all_grid_handles: set[int] = set()
    unresolved: set[int] = set()
    warnings: list[str] = []
    owned_set = set(owned)
    # Real saves may pad the owned array with repeated 0xFFFFFFFF sentinels;
    # keep that observed placeholder as a warning-free non-object value while
    # still flagging duplicate live handles as unresolved.
    duplicate_owned = {h for h in owned if h != 0xFFFFFFFF and owned.count(h) > 1}
    if duplicate_owned:
        unresolved.update(duplicate_owned)
        warnings.append(
            "Owned handle list содержит дубликаты: "
            + ", ".join(f"0x{h:08X}" for h in sorted(duplicate_owned))
        )
    grid_positions: dict[tuple[int, int], int] = {}
    for i in range(grid_count):
        off = grid_off + i * GRID_RECORD_SIZE
        handle, x, y = struct.unpack_from("<IHH", raw, off)
        all_grid_handles.add(handle)
        if handle not in owned_set:
            unresolved.add(handle)
            warnings.append(
                f"Grid cell #{i} ссылается на handle, которого нет в owned list: 0x{handle:08X}"
            )
            continue
        if (handle >> 24) != 0x30 or x >= GRID_WIDTH or y >= 128:
            unresolved.add(handle)
            warnings.append(
                f"Grid cell #{i} вне поддерживаемых границ: handle=0x{handle:08X}, x={x}, y={y}"
            )
            continue
        previous = grid_positions.get((x, y))
        if previous is not None:
            unresolved.update((previous, handle))
            warnings.append(
                f"Duplicate grid position {x},{y}: handles 0x{previous:08X} и 0x{handle:08X}"
            )
        else:
            grid_positions[(x, y)] = handle
        cells.append(GridCell(handle, x, y))
    if grid_count == 0:
        warnings.append("Inventory grid пуст: отображены только owned handles")

    return InventoryLayout(
        anchor_offset=anchor,
        money_offset=money_off,
        owned_flag_offset=flag_off,
        owned_count_offset=count_off,
        owned_handles_offset=handles_off,
        owned_handles=tuple(owned),
        grid_count_offset=grid_count_off,
        grid_offset=grid_off,
        grid_cells=tuple(cells),
        grid_end_offset=grid_end,
        declared_grid_count=grid_count,
        grid_handle_count=len(all_grid_handles),
        unresolved_handles=tuple(sorted(unresolved)),
        warnings=tuple(warnings),
    )


def _candidate_object_records(raw: bytes, handle: int) -> list[tuple[int, int, float, int]]:
    needle = struct.pack("<I", handle)
    out: list[tuple[int, int, float, int]] = []
    start = 0
    while True:
        i = raw.find(needle, start)
        if i < 0:
            break
        start = i + 1
        if i + 36 > len(raw):
            continue
        if raw[i + STACK_MARKER_OFFSET] != 0x38:
            continue
        count = struct.unpack_from("<I", raw, i + STACK_COUNT_OFFSET)[0]
        weight = struct.unpack_from("<f", raw, i + STACK_WEIGHT_OFFSET)[0]
        kind = raw[i + STACK_KIND_OFFSET]
        if not (1 <= count <= 10_000_000):
            continue
        if not math.isfinite(weight) or weight < 0 or weight > 10_000_000:
            continue
        out.append((i, count, weight, kind))
    return out


def locate_object_record(raw: bytes, handle: int) -> tuple[int, int, float, int]:
    c = _candidate_object_records(raw, handle)
    if len(c) != 1:
        raise SaveError(
            f"Object record 0x{handle:08X}: найдено {len(c)} кандидатов, ожидался 1"
        )
    return c[0]


def _record_start_map(raw: bytes, handles: Iterable[int]) -> dict[int, int]:
    out: dict[int, int] = {}
    for h in handles:
        c = _candidate_object_records(raw, h)
        if len(c) == 1:
            out[h] = c[0][0]
    return out


def _record_end_guesses(raw: bytes, starts: dict[int, int]) -> dict[int, int]:
    """Conservative record-end guesses for lab/debug hex views only.

    We do NOT use these boundaries for structural insertion/deletion. They are
    simply the next confirmed owned-object record start, capped at 64 KiB.
    """
    pairs = sorted((off, h) for h, off in starts.items())
    result: dict[int, int] = {}
    for idx, (off, h) in enumerate(pairs):
        next_off = pairs[idx + 1][0] if idx + 1 < len(pairs) else min(len(raw), off + 4096)
        result[h] = min(next_off, off + 65536)
    return result


_S2_NAME_TABLE_MAX_ENTRIES = 8192
_S2_NAME_MAX_BYTES = 4096


def _decode_s2_name(value: bytes) -> str | None:
    """Decode one embedded S2 name without accepting binary table data."""

    try:
        decoded = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if any(not character.isprintable() and character not in "\t" for character in decoded):
        return None
    return decoded


def _parse_s2_name_table(raw: bytes | bytearray, start: int) -> tuple[str, ...] | None:
    """Parse one counted UTF-8 string array at ``start`` if it is complete."""

    if start < 0 or start + 2 > len(raw):
        return None
    count = struct.unpack_from("<H", raw, start)[0]
    if not (1 <= count <= _S2_NAME_TABLE_MAX_ENTRIES):
        return None

    offset = start + 2
    names: list[str] = []
    for _ in range(count):
        if offset + 2 > len(raw):
            return None
        byte_count = struct.unpack_from("<H", raw, offset)[0]
        if byte_count > _S2_NAME_MAX_BYTES or offset + 2 + byte_count > len(raw):
            return None
        value = _decode_s2_name(bytes(raw[offset + 2 : offset + 2 + byte_count]))
        if value is None:
            return None
        names.append(value)
        offset += 2 + byte_count
    return tuple(names)


def locate_s2_item_name_table(
    raw: bytes | bytearray,
    type_keys: Iterable[bytes] = (),
) -> S2NameTables | None:
    """Locate the save-local item name tables used by the S2 compact key.

    The observed S2 saves serialize a run of counted string tables; the one
    whose first entry is ``GunAK74_ST`` is selected by key byte 4 and the
    tables that follow it by 5, 6, …  The low two bytes of a ``type_key``
    index into the selected table.  This exposes save-local display metadata
    only; it does not turn an entry into a public SID or a constructor.
    """

    keys = [bytes(key) for key in type_keys if len(key) == 3]
    needle = struct.pack("<H", len(b"GunAK74_ST")) + b"GunAK74_ST"
    search_from = 0
    while True:
        name_offset = raw.find(needle, search_from)
        if name_offset < 0:
            return None
        # ``name_offset`` points at the u16 byte length immediately after the
        # table's u16 entry count.
        table_start = name_offset - 2
        names = _parse_s2_name_table(raw, table_start)
        if names is not None and names[0] == "GunAK74_ST":
            tables = [names]
            offset = table_start + 2 + sum(2 + len(name.encode("utf-8")) for name in names)
            while len(tables) < 16:
                following = _parse_s2_name_table(raw, offset)
                if following is None:
                    break
                tables.append(following)
                offset += 2 + sum(2 + len(name.encode("utf-8")) for name in following)
            found = S2NameTables(tables)
            if not keys or any(found.resolve(key) is not None for key in keys):
                return found
        search_from = name_offset + 1


def _s2_display_name(
    name_table: Sequence[str] | None,
    type_key: bytes,
) -> str | None:
    if name_table is None or len(type_key) != 3:
        return None
    return s2_name_for_key(bytes(type_key), name_table)


def _inventory_details(
    raw: bytes, layout: InventoryLayout | None = None
) -> tuple[tuple[InventoryItem, ...], tuple[int, ...], tuple[str, ...]]:
    layout = layout or locate_inventory_layout(raw)
    cells_by_handle: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for c in layout.grid_cells:
        cells_by_handle[c.handle].append((c.x, c.y))

    starts = _record_start_map(raw, layout.owned_handles)
    ends = _record_end_guesses(raw, starts)
    name_table = locate_s2_item_name_table(
        raw,
        tuple(raw[offset + 8 : offset + 11] for offset in starts.values()),
    )
    items: list[InventoryItem] = []
    unresolved = set(layout.unresolved_handles)
    warnings = list(layout.warnings)
    for handle, cells in cells_by_handle.items():
        candidates = _candidate_object_records(raw, handle)
        if len(candidates) != 1:
            unresolved.add(handle)
            warnings.append(
                f"Inventory handle 0x{handle:08X}: object record candidates={len(candidates)}"
            )
            continue
        rec_off, count, total_weight, kind = candidates[0]
        xs = [p[0] for p in cells]
        ys = [p[1] for p in cells]
        x0, y0 = min(xs), min(ys)
        width, height = max(xs) - x0 + 1, max(ys) - y0 + 1
        expected_cells = {
            (x, y)
            for y in range(y0, y0 + height)
            for x in range(x0, x0 + width)
        }
        if set(cells) != expected_cells or len(set(cells)) != len(cells):
            unresolved.add(handle)
            warnings.append(
                f"Handle 0x{handle:08X}: footprint/коллизия grid cells не образует полный прямоугольник"
            )
        unit_weight = total_weight / count if count else 0.0
        if kind not in KNOWN_KIND_CODES:
            unresolved.add(handle)
            warnings.append(
                f"Handle 0x{handle:08X}: неизвестный object kind={kind}, только read-only"
            )
        # A single consumable, round or grenade uses the same stack record as a
        # pile of them, so its count is as safe to change as any stack.
        editable = handle not in unresolved and (
            (count > 1 and kind in EDITABLE_STACK_KIND_CODES) or (count >= 1 and kind in SINGLE_STACK_KIND_CODES)
        )
        fingerprint = raw[rec_off + 4 : rec_off + 18].hex()
        # The first byte remains an opaque S2 serialization discriminator. The
        # lower two bytes resolve through the save-local name table when the
        # table is present; neither field is claimed to be a public SID/hash.
        type_key = raw[rec_off + 8 : rec_off + 11].hex()
        display_name = _s2_display_name(name_table, raw[rec_off + 8 : rec_off + 11])
        condition = None
        condition_editable = False
        modules = None
        upgrades = None
        if kind == 0 and name_table is not None:
            weapon_anchor = read_s2_weapon_condition(
                raw,
                handle=handle,
                record_offset=rec_off,
                record_end=ends.get(handle),
                kind_code=kind,
                name_table=name_table,
            )
            if weapon_anchor is not None:
                condition = weapon_anchor.value
                condition_editable = True
                modules = weapon_anchor.modules
                upgrades = weapon_anchor.upgrades
        items.append(
            InventoryItem(
                handle=handle,
                x=x0,
                y=y0,
                width=width,
                height=height,
                cells=tuple(sorted(set(cells), key=lambda p: (p[1], p[0]))),
                count=count,
                total_weight=total_weight,
                unit_weight=unit_weight,
                kind_code=kind,
                category=_s2_category_name(kind, display_name),
                record_offset=rec_off,
                record_end_guess=ends.get(handle, min(len(raw), rec_off + 512)),
                fingerprint=fingerprint,
                type_key=type_key,
                editable_count=editable,
                display_name=display_name,
                condition=condition,
                condition_editable=condition_editable,
                storage="inventory",
                observation_source="grid",
                modules=modules,
                upgrades=upgrades,
            )
        )
    # Equipped items are actor-owned but intentionally absent from the grid.
    # Only the observed nested same-handle shape is enough to distinguish them
    # from ordinary orphan records; synthetic/unknown records stay orphaned.
    grid_handles = {cell.handle for cell in layout.grid_cells}
    for handle in layout.owned_handles:
        if handle == 0xFFFFFFFF or handle in grid_handles or handle in unresolved:
            continue
        candidates = _candidate_object_records(raw, handle)
        if len(candidates) != 1:
            continue
        rec_off, count, total_weight, kind = candidates[0]
        carried = kind in S2_CARRIED_KIND_CODES
        if not carried and (
            kind not in S2_EQUIPMENT_KIND_CODES
            or not has_s2_equipment_shape(
                raw,
                handle=handle,
                record_offset=rec_off,
                kind_code=kind,
            )
        ):
            continue
        type_key_bytes = raw[rec_off + 8 : rec_off + 11]
        display_name = _s2_display_name(name_table, type_key_bytes)
        condition = None
        condition_editable = False
        modules = None
        upgrades = None
        if kind == 1:
            condition_anchor = read_s2_armor_condition(
                raw,
                handle=handle,
                record_offset=rec_off,
                kind_code=kind,
            )
            if condition_anchor is not None:
                condition = condition_anchor.value
                condition_editable = _s2_armor_name(display_name)
                if name_table is not None:
                    upgrades = read_s2_armor_upgrades(
                        raw, anchor=condition_anchor, name_table=name_table
                    ) or None
            else:
                warnings.append(
                    f"Equipped handle 0x{handle:08X}: S2 armor condition не подтверждён"
                )
        elif kind == 0 and name_table is not None:
            weapon_anchor = read_s2_weapon_condition(
                raw,
                handle=handle,
                record_offset=rec_off,
                record_end=ends.get(handle),
                kind_code=kind,
                name_table=name_table,
            )
            if weapon_anchor is not None:
                condition = weapon_anchor.value
                condition_editable = True
                modules = weapon_anchor.modules
                upgrades = weapon_anchor.upgrades
        items.append(
            InventoryItem(
                handle=handle,
                x=None,
                y=None,
                width=None,
                height=None,
                cells=(),
                count=count,
                total_weight=total_weight,
                unit_weight=total_weight / count if count else 0.0,
                kind_code=kind,
                category=_s2_category_name(kind, display_name),
                record_offset=rec_off,
                record_end_guess=ends.get(handle, min(len(raw), rec_off + 512)),
                fingerprint=raw[rec_off + 4 : rec_off + 18].hex(),
                type_key=type_key_bytes.hex(),
                editable_count=False,
                display_name=display_name,
                position_label="у персонажа" if carried else "экипировано",
                size_label="неизвестно",
                count_max=1_000_000,
                condition=condition,
                condition_editable=condition_editable,
                storage="equipped",
                observation_source="carried" if carried else "equipped",
                modules=modules,
                upgrades=upgrades,
            )
        )
    items.sort(key=lambda it: (it.y is None, it.y or 0, it.x is None, it.x or 0, it.handle))
    if not items and layout.declared_grid_count:
        warnings.append("Не удалось сопоставить ни одной grid cell с object record")
    for handle in layout.owned_handles:
        if handle == 0xFFFFFFFF or handle in {c.handle for c in layout.grid_cells} or handle in unresolved:
            continue
        candidates = _candidate_object_records(raw, handle)
        if len(candidates) != 1:
            unresolved.add(handle)
            warnings.append(
                f"Owned handle 0x{handle:08X}: отсутствует однозначный object record"
            )
    deduped_warnings = tuple(dict.fromkeys(warnings))
    return tuple(items), tuple(sorted(unresolved)), deduped_warnings


def locate_inventory(raw: bytes) -> tuple[InventoryItem, ...]:
    return _inventory_details(raw)[0]


def locate_orphans(raw: bytes) -> tuple[OrphanItem, ...]:
    layout = locate_inventory_layout(raw)
    grid_handles = {c.handle for c in layout.grid_cells}
    out: list[OrphanItem] = []
    for h in layout.owned_handles:
        if h == 0xFFFFFFFF or h in grid_handles or h in layout.unresolved_handles:
            continue
        c = _candidate_object_records(raw, h)
        if len(c) != 1:
            continue
        rec_off, count, weight, kind = c[0]
        if has_s2_equipment_shape(
            raw,
            handle=h,
            record_offset=rec_off,
            kind_code=kind,
        ):
            continue
        x = struct.unpack_from("<H", raw, rec_off + OBJ_POS_X_OFFSET)[0]
        y = struct.unpack_from("<H", raw, rec_off + OBJ_POS_Y_OFFSET)[0]
        out.append(
            OrphanItem(
                handle=h,
                record_offset=rec_off,
                x=x,
                y=y,
                count=count,
                total_weight=weight,
                kind_code=kind,
                category=_category_name(kind),
                type_key=raw[rec_off + 8 : rec_off + 11].hex(),
            )
        )
    return tuple(out)


def inspect_save(data: bytes, with_inventory: bool = True) -> SaveInfo:
    stored, computed, ok = validate_crc(data)
    if not ok:
        raise SaveError(
            f"CRC32 исходного сейва не совпадает: stored={stored:08x}, computed={computed:08x}"
        )
    raw = decompress_save(data)
    anchor_count = raw.count(MONEY_ANCHOR)
    money = None
    if anchor_count == 1:
        _, money = locate_money(raw)
    inventory: tuple[InventoryItem, ...] = ()
    owned: tuple[int, ...] = ()
    grid_cells = 0
    grid_handles = 0
    orphans: tuple[OrphanItem, ...] = ()
    unresolved: tuple[int, ...] = ()
    warnings: list[str] = []
    if anchor_count != 1:
        warnings.append(f"Wallet anchor count={anchor_count}; money is not editable")
    if with_inventory:
        layout = locate_inventory_layout(raw)
        owned = layout.owned_handles
        grid_cells = layout.declared_grid_count
        grid_handles = layout.grid_handle_count
        inventory, unresolved, layout_warnings = _inventory_details(raw, layout)
        warnings.extend(layout_warnings)
        orphans = locate_orphans(raw)
        unresolved_set = set(unresolved)
        for orphan in orphans:
            if orphan.kind_code not in KNOWN_KIND_CODES:
                unresolved_set.add(orphan.handle)
                warnings.append(
                    f"Handle 0x{orphan.handle:08X}: неизвестный orphan object kind={orphan.kind_code}, только read-only"
                )
        unresolved = tuple(sorted(unresolved_set))
    return SaveInfo(
        packed_size=len(data),
        unpacked_size=len(raw),
        stored_crc32=stored,
        computed_crc32=computed,
        crc_ok=ok,
        sha256=hashlib.sha256(data).hexdigest(),
        money=money,
        money_anchor_count=anchor_count,
        inventory=inventory,
        owned_handles=owned,
        grid_cell_count=grid_cells,
        orphans=orphans,
        grid_handle_count=grid_handles,
        unresolved_handles=unresolved,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def rebuild_uncompressed(raw: bytes) -> bytes:
    stream = bytearray()
    for off in range(0, len(raw), BLOCK_SIZE):
        stream += UNCOMPRESSED_BLOCK_HEADER
        stream += raw[off : off + BLOCK_SIZE]
    out = bytearray(struct.pack("<I", len(raw)))
    out += stream
    crc = zlib.crc32(out) & 0xFFFFFFFF
    out += struct.pack("<I", crc)
    return bytes(out)


def rebuild_compact(
    source_data: bytes,
    raw: bytes,
    *,
    original_raw: bytes | None = None,
) -> tuple[bytes, CompactRebuildResult]:
    """Rebuild a save with the native encoder when the desktop build has one.

    Source blocks remain the safe metadata decision.  Changed payloads are
    re-encoded as one valid Kraken stream when ``ooz_encoder`` is available;
    an edited compressed source is rejected when the encoder is unavailable.
    Keeping that old source-only/browser fallback for a compressed save would
    silently produce the 15--18 MB stored-block artifact that Steam/game
    loading may reject.  Already-uncompressed fixtures remain supported without
    an encoder.
    """

    stored, computed, ok = validate_crc(source_data)
    if not ok:
        raise SaveError(
            f"Отказ от пересборки: CRC32 исходника плохой ({stored:08x} != {computed:08x})"
        )
    unpacked_size = struct.unpack_from("<I", source_data, 0)[0]
    before = decompress_save(source_data) if original_raw is None else bytes(original_raw)
    if len(before) != unpacked_size:
        raise SaveError(
            f"Исходный raw имеет размер {len(before)} вместо заголовка {unpacked_size}"
        )
    after = bytes(raw)
    try:
        decision = compact_rebuild_stream(
            source_data[4:-4], original_raw=before, new_raw=after
        )
    except KrakenBlocksError as exc:
        raise SaveError(f"Kraken compact rebuild не удался: {exc}") from exc

    stream = decision.stream
    reason = decision.reason
    if decision.mode != "unchanged":
        try:
            stream = codec_compress(after, level=5)
        except CodecError as exc:
            try:
                source_layout = parse_kraken_stream(source_data[4:-4], len(before))
            except KrakenBlocksError:
                raise SaveError(
                    "Сохранение изменено, но compact Kraken encoder недоступен, "
                    "а исходный поток не удалось доказанно разобрать; "
                    "раздутая CC06-пересборка запрещена"
                ) from exc
            if any(not block.uncompressed for block in source_layout.blocks):
                raise SaveError(
                    "Сохранение изменено, но compact Kraken encoder недоступен; "
                    "раздутая CC06-пересборка запрещена. Установите/используйте "
                    "desktop build с ooz_encoder."
                ) from exc
            reason = (
                f"{reason}; native Kraken encoder unavailable ({exc}); "
                "исходный поток уже состоит из uncompressed CC06 blocks"
            )
        else:
            reason = (
                f"{reason}; changed payload re-encoded with native Kraken encoder"
            )

    decision = CompactRebuildResult(
        stream=stream,
        mode=decision.mode,
        preserved_blocks=decision.preserved_blocks,
        rebuilt_blocks=decision.rebuilt_blocks,
        reason=reason,
    )
    body = struct.pack("<I", len(after)) + decision.stream
    rebuilt = body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)
    return rebuilt, decision


def _patch_stack_in_raw(raw: bytearray, handle: int, new_count: int) -> tuple[int, int]:
    if not (1 <= new_count <= 1_000_000):
        raise SaveError("Количество предмета должно быть от 1 до 1 000 000")
    items = {it.handle: it for it in locate_inventory(bytes(raw))}
    item = items.get(handle)
    if item is None:
        raise SaveError(f"Inventory handle 0x{handle:08X} больше не найден")
    if not item.editable_count:
        raise SaveError(
            f"Handle 0x{handle:08X} не помечен как безопасный stack (count={item.count}, kind={item.kind_code})"
        )
    if item.count is None or item.unit_weight is None:
        raise SaveError(f"Handle 0x{handle:08X}: count/weight не подтверждены")
    old_count = item.count
    new_total_weight = item.unit_weight * new_count
    if not math.isfinite(new_total_weight) or new_total_weight > 10_000_000:
        raise SaveError("Новый суммарный вес стека вышел за безопасный диапазон")
    struct.pack_into("<I", raw, item.record_offset + STACK_COUNT_OFFSET, new_count)
    struct.pack_into("<f", raw, item.record_offset + STACK_WEIGHT_OFFSET, new_total_weight)
    return old_count, new_count


def _patch_move_in_raw(raw: bytearray, handle: int, new_x: int, new_y: int) -> tuple[int, int, int, int]:
    if not (0 <= new_x < GRID_WIDTH and 0 <= new_y < 128):
        raise SaveError("Новая позиция вне допустимой inventory grid")
    items_tuple, unresolved, _warnings = _inventory_details(bytes(raw))
    if unresolved:
        raise SaveError(
            "Move остановлен: inventory содержит unresolved handles "
            + ", ".join(f"0x{h:08X}" for h in unresolved)
        )
    items = {it.handle: it for it in items_tuple}
    item = items.get(handle)
    if item is None:
        raise SaveError(f"Inventory handle 0x{handle:08X} не найден")
    if item.x is None or item.y is None or item.width is None or item.height is None:
        raise SaveError(f"Предмет 0x{handle:08X}: position/size не подтверждены")
    max_x = new_x + item.width - 1
    max_y = new_y + item.height - 1
    if max_x >= GRID_WIDTH or max_y >= 128:
        raise SaveError(f"Предмет {item.size_text} не помещается в позицию {new_x},{new_y}")

    layout = locate_inventory_layout(bytes(raw))
    occupied = {(c.x, c.y): c.handle for c in layout.grid_cells if c.handle != handle}
    rel = [(x - item.x, y - item.y) for x, y in item.cells]
    targets = [(new_x + dx, new_y + dy) for dx, dy in rel]
    for p in targets:
        if p in occupied:
            raise SaveError(f"Ячейка {p[0]},{p[1]} занята handle 0x{occupied[p]:08X}")

    # Patch all grid records for this handle in-place.
    idx = 0
    for cell_i, c in enumerate(layout.grid_cells):
        if c.handle != handle:
            continue
        gx, gy = targets[idx]
        off = layout.grid_offset + cell_i * GRID_RECORD_SIZE
        struct.pack_into("<HH", raw, off + 4, gx, gy)
        idx += 1
    if idx != len(targets):
        raise SaveError("Внутренняя ошибка перемещения: число cell records изменилось")

    rec_off, *_ = locate_object_record(bytes(raw), handle)
    struct.pack_into("<H", raw, rec_off + OBJ_POS_X_OFFSET, new_x)
    struct.pack_into("<H", raw, rec_off + OBJ_POS_Y_OFFSET, new_y)
    return item.x, item.y, new_x, new_y


def _rebuild_inventory_arrays(
    raw: bytes,
    *,
    owned_handles: Iterable[int] | None = None,
    grid_cells: Iterable[GridCell] | None = None,
) -> bytes:
    layout = locate_inventory_layout(raw)
    if layout.unresolved_handles:
        raise SaveError(
            "Нельзя пересобирать inventory при unresolved grid handles: "
            + ", ".join(f"0x{h:08X}" for h in layout.unresolved_handles)
        )
    owned = tuple(layout.owned_handles if owned_handles is None else owned_handles)
    cells = tuple(layout.grid_cells if grid_cells is None else grid_cells)
    if len(owned) > 0xFFFF or len(cells) > 0xFFFF:
        raise SaveError("Inventory array слишком большой для u16 count")
    middle = bytearray()
    middle += struct.pack("<H", len(owned))
    for h in owned:
        middle += struct.pack("<I", h)
    middle += struct.pack("<H", len(cells))
    for c in cells:
        middle += struct.pack("<IHH", c.handle, c.x, c.y)
    return raw[: layout.owned_count_offset] + bytes(middle) + raw[layout.grid_end_offset :]


def _detach_in_raw(raw: bytes, handle: int, deep: bool) -> bytes:
    layout = locate_inventory_layout(raw)
    _items, unresolved, _warnings = _inventory_details(raw, layout)
    if handle in unresolved:
        raise SaveError(f"Detach запрещён для unresolved handle 0x{handle:08X}")
    if not any(c.handle == handle for c in layout.grid_cells):
        raise SaveError(f"Handle 0x{handle:08X} уже отсутствует в inventory grid")
    rec_off, *_ = locate_object_record(raw, handle)
    mutable = bytearray(raw)
    struct.pack_into("<H", mutable, rec_off + OBJ_POS_X_OFFSET, 0xFFFF)
    struct.pack_into("<H", mutable, rec_off + OBJ_POS_Y_OFFSET, 0xFFFF)
    raw = bytes(mutable)
    layout = locate_inventory_layout(raw)
    cells = tuple(c for c in layout.grid_cells if c.handle != handle)
    owned = layout.owned_handles
    if deep:
        owned = tuple(h for h in owned if h != handle)
    return _rebuild_inventory_arrays(raw, owned_handles=owned, grid_cells=cells)


def _attach_orphan_in_raw(raw: bytes, handle: int, x: int, y: int, width: int, height: int) -> bytes:
    if not (1 <= width <= GRID_WIDTH and 1 <= height <= 16):
        raise SaveError("Для experimental attach укажи width 1..8 и height 1..16")
    if not (0 <= x < GRID_WIDTH and 0 <= y < 128):
        raise SaveError("Позиция attach вне grid")
    if x + width > GRID_WIDTH or y + height > 128:
        raise SaveError("Footprint attach не помещается в grid")
    layout = locate_inventory_layout(raw)
    if layout.unresolved_handles:
        raise SaveError(
            "Attach остановлен: inventory содержит unresolved grid handles "
            + ", ".join(f"0x{h:08X}" for h in layout.unresolved_handles)
        )
    if handle not in layout.owned_handles:
        raise SaveError("Attach допускает только handle, который уже есть в owned handle list")
    if any(c.handle == handle for c in layout.grid_cells):
        raise SaveError("Handle уже находится в grid")
    _record_off, _count, _weight, kind = locate_object_record(raw, handle)
    if kind not in KNOWN_KIND_CODES:
        raise SaveError(f"Attach запрещён для неизвестного object kind={kind}")
    occupied = {(c.x, c.y) for c in layout.grid_cells}
    new_cells = [GridCell(handle, x + dx, y + dy) for dy in range(height) for dx in range(width)]
    for c in new_cells:
        if (c.x, c.y) in occupied:
            raise SaveError(f"Attach: ячейка {c.x},{c.y} уже занята")
    mutable = bytearray(raw)
    rec_off, *_ = locate_object_record(raw, handle)
    struct.pack_into("<H", mutable, rec_off + OBJ_POS_X_OFFSET, x)
    struct.pack_into("<H", mutable, rec_off + OBJ_POS_Y_OFFSET, y)
    raw2 = bytes(mutable)
    layout2 = locate_inventory_layout(raw2)
    return _rebuild_inventory_arrays(raw2, grid_cells=tuple(layout2.grid_cells) + tuple(new_cells))


# --- S2 player stash (S2-STASH, ED-2 stage 1) ------------------------------
# Evidence docs/evidence/S2_ADD_2026-09-26.md: the stash follows the player
# inventory arrays with the same shape; taken items leave 0xFFFFFFFF slots in
# its owned list and lose their grid cells, and their record drops the
# "in stash" byte (+15) and bit 0x08 of byte +28.
_STASH_MARKER = b"\xff\xff\xff\xff\x06\x01\x00\x00\x00\x06"
_STASH_SEARCH_WINDOW = 512
STASH_TOMBSTONE = 0xFFFFFFFF
OBJ_STASH_FLAG_OFFSET = 15
OBJ_FLAGS_OFFSET = 28
OBJ_FLAGS_STASH_BIT = 0x08


@dataclass(frozen=True)
class StashLayout:
    owned_count_offset: int
    owned_handles: tuple[int, ...]
    grid_cells: tuple[GridCell, ...]
    grid_end_offset: int

    @property
    def live_handles(self) -> tuple[int, ...]:
        return tuple(h for h in self.owned_handles if h != STASH_TOMBSTONE)


def locate_stash_layout(raw: bytes) -> StashLayout:
    """Parse the S2 player stash right after the player inventory arrays."""

    player = locate_inventory_layout(raw)
    start = player.grid_end_offset
    marker = raw.find(_STASH_MARKER, start, start + _STASH_SEARCH_WINDOW)
    if marker < 0 or raw.find(_STASH_MARKER, marker + 1, start + _STASH_SEARCH_WINDOW) >= 0:
        raise SaveError("S2 stash: заголовок тайника не найден однозначно")
    count_offset = marker + 20
    if raw[marker + 16 : count_offset] != b"\x03\x00\x00\x00":
        raise SaveError("S2 stash: неизвестная форма заголовка тайника")
    (count,) = struct.unpack_from("<H", raw, count_offset)
    handles = struct.unpack_from(f"<{count}I", raw, count_offset + 2)
    grid_offset = count_offset + 2 + 4 * count
    (cell_count,) = struct.unpack_from("<H", raw, grid_offset)
    cells = tuple(
        GridCell(*struct.unpack_from("<IHH", raw, grid_offset + 2 + 8 * index))
        for index in range(cell_count)
    )
    live = {h for h in handles if h != STASH_TOMBSTONE}
    if any(h >> 16 != 0x3000 for h in live) or any(c.handle not in live for c in cells):
        raise SaveError("S2 stash: список или сетка тайника не согласованы")
    return StashLayout(count_offset, tuple(handles), cells, grid_offset + 2 + 8 * cell_count)


def _free_player_spot(occupied: set[tuple[int, int]], shape: list[tuple[int, int]]) -> tuple[int, int]:
    for y in range(128):
        for x in range(GRID_WIDTH):
            if all(0 <= x + dx < GRID_WIDTH and (x + dx, y + dy) not in occupied for dx, dy in shape):
                return x, y
    raise SaveError("В рюкзаке нет свободного места под предмет")


def _stash_to_player_in_raw(raw: bytes, handle: int) -> bytes:
    """Move one stash item into the backpack exactly as the game records it."""

    stash = locate_stash_layout(raw)
    if handle not in stash.live_handles:
        raise SaveError(f"Handle 0x{handle:08X} не лежит в тайнике")
    player = locate_inventory_layout(raw)
    if player.unresolved_handles:
        raise SaveError("Перенос остановлен: в инвентаре есть unresolved handles")
    if handle in player.owned_handles:
        raise SaveError(f"Handle 0x{handle:08X} уже принадлежит игроку")
    rec_off, _count, _weight, kind = locate_object_record(raw, handle)
    if kind not in KNOWN_KIND_CODES | {3}:
        raise SaveError(f"Перенос запрещён для неизвестного object kind={kind}")
    if raw[rec_off + OBJ_STASH_FLAG_OFFSET] != 1 or not raw[rec_off + OBJ_FLAGS_OFFSET] & OBJ_FLAGS_STASH_BIT:
        raise SaveError(f"Запись 0x{handle:08X} не помечена как предмет тайника")
    own = [c for c in stash.grid_cells if c.handle == handle]
    if not own:
        raise SaveError(f"Handle 0x{handle:08X} не размещён в сетке тайника")
    base_x = min(c.x for c in own)
    base_y = min(c.y for c in own)
    shape = sorted((c.x - base_x, c.y - base_y) for c in own)
    x, y = _free_player_spot({(c.x, c.y) for c in player.grid_cells}, shape)

    mutable = bytearray(raw)
    struct.pack_into("<H", mutable, rec_off + OBJ_POS_X_OFFSET, x)
    struct.pack_into("<H", mutable, rec_off + OBJ_POS_Y_OFFSET, y)
    mutable[rec_off + OBJ_STASH_FLAG_OFFSET] = 0
    mutable[rec_off + OBJ_FLAGS_OFFSET] &= ~OBJ_FLAGS_STASH_BIT & 0xFF
    # Stash first: it lies after the player arrays, so its offsets stay valid.
    slot = stash.owned_handles.index(handle)
    struct.pack_into("<I", mutable, stash.owned_count_offset + 2 + 4 * slot, STASH_TOMBSTONE)
    cells_offset = stash.owned_count_offset + 2 + 4 * len(stash.owned_handles)
    kept = [c for c in stash.grid_cells if c.handle != handle]
    stash_grid = struct.pack("<H", len(kept)) + b"".join(struct.pack("<IHH", c.handle, c.x, c.y) for c in kept)
    raw = bytes(mutable[:cells_offset]) + stash_grid + bytes(mutable[stash.grid_end_offset :])
    player = locate_inventory_layout(raw)
    return _rebuild_inventory_arrays(
        raw,
        owned_handles=(*player.owned_handles, handle),
        grid_cells=(*player.grid_cells, *(GridCell(handle, x + dx, y + dy) for dx, dy in shape)),
    )


def _patch_s2_durability_in_raw(
    raw: bytearray,
    handle: int,
    condition: float,
) -> None:
    """Patch one confirmed S2 armor/weapon condition at its exact anchor."""

    layout = locate_inventory_layout(bytes(raw))
    if handle not in layout.owned_handles or handle in layout.unresolved_handles:
        raise SaveError(
            f"S2 armor handle 0x{handle:08X} не является однозначным actor-owned item"
        )
    items, _unresolved, _warnings = _inventory_details(bytes(raw), layout)
    confirmed = next(
        (item for item in items if item.handle == handle and item.condition_editable),
        None,
    )
    if confirmed is None:
        raise SaveError(
            f"S2 condition для handle 0x{handle:08X} не подтверждён parser-ом"
        )
    record_offset = confirmed.record_offset
    kind = confirmed.kind_code
    try:
        if kind == 1:
            if not _s2_armor_name(confirmed.display_name):
                raise SaveError(
                    f"S2 armor condition для handle 0x{handle:08X} не подтверждён exact armor name"
                )
            if not has_s2_equipment_shape(
                raw,
                handle=handle,
                record_offset=record_offset,
                kind_code=kind,
            ):
                raise SaveError(
                    f"S2 armor condition для handle 0x{handle:08X} не имеет подтверждённой формы"
                )
            patch_s2_armor_condition(
                raw,
                handle=handle,
                record_offset=record_offset,
                kind_code=kind,
                value=condition,
            )
            return
        if kind == 0:
            raw_bytes = bytes(raw)
            starts = _record_start_map(raw_bytes, layout.owned_handles)
            name_table = locate_s2_item_name_table(
                raw_bytes,
                tuple(raw_bytes[offset + 8 : offset + 11] for offset in starts.values()),
            )
            if name_table is None:
                raise SaveError(
                    f"S2 weapon condition для handle 0x{handle:08X}: name table не подтверждена"
                )
            patch_s2_weapon_condition(
                raw,
                handle=handle,
                record_offset=record_offset,
                record_end=confirmed.record_end_guess,
                kind_code=kind,
                name_table=name_table,
                value=condition,
            )
            return
        raise SaveError(
            f"S2 condition для handle 0x{handle:08X}: kind={kind} не является оружием или бронёй"
        )
    except ValueError as exc:
        raise SaveError(f"S2 condition для 0x{handle:08X} не разобран: {exc}") from exc


def _encode_raw_patch(patch: RawPatch) -> bytes:
    k = patch.kind.lower().strip()
    v = patch.value.strip()
    try:
        if k == "u8":
            return struct.pack("<B", int(v, 0))
        if k == "u16":
            return struct.pack("<H", int(v, 0))
        if k == "u32":
            return struct.pack("<I", int(v, 0))
        if k == "i32":
            return struct.pack("<i", int(v, 0))
        if k == "f32":
            return struct.pack("<f", float(v))
        if k == "hex":
            cleaned = v.replace(" ", "").replace("_", "")
            return bytes.fromhex(cleaned)
    except Exception as exc:
        raise SaveError(f"Bad raw patch {patch}: {exc}") from exc
    raise SaveError(f"Неизвестный raw patch type: {patch.kind}")


def _apply_raw_patch(raw: bytearray, patch: RawPatch) -> None:
    blob = _encode_raw_patch(patch)
    if patch.offset < 0 or patch.offset + len(blob) > len(raw):
        raise SaveError(f"Raw patch выходит за payload: 0x{patch.offset:X}+{len(blob)}")
    raw[patch.offset : patch.offset + len(blob)] = blob


def record_hex(raw: bytes, handle: int, limit: int = 512) -> tuple[int, bytes]:
    """Return a lab/debug hex slice from one confirmed object record."""
    layout = locate_inventory_layout(raw)
    starts = _record_start_map(raw, layout.owned_handles)
    if handle not in starts:
        raise SaveError(f"Record 0x{handle:08X} не найден однозначно")
    ends = _record_end_guesses(raw, starts)
    off = starts[handle]
    end = min(ends[handle], off + max(32, limit))
    return off, raw[off:end]


def diff_record(save_a_raw: bytes, save_b_raw: bytes, handle: int, limit: int = 2048) -> list[tuple[int, bytes, bytes]]:
    # Offsets are reported relative to each record, so the absolute bases of
    # the two saves are deliberately unused here.
    _, a = record_hex(save_a_raw, handle, limit)
    _, b = record_hex(save_b_raw, handle, limit)
    n = min(len(a), len(b))
    diffs = [i for i in range(n) if a[i] != b[i]]
    if len(a) != len(b):
        diffs.extend(range(n, max(len(a), len(b))))
    if not diffs:
        return []
    groups: list[tuple[int, int]] = []
    s = p = diffs[0]
    for d in diffs[1:]:
        if d == p + 1:
            p = d
        else:
            groups.append((s, p))
            s = p = d
    groups.append((s, p))
    out = []
    for s, e in groups:
        out.append((s, a[s : min(e + 1, len(a))], b[s : min(e + 1, len(b))]))
    return out


def patch_save(
    data: bytes,
    *,
    new_money: int | None = None,
    stack_counts: dict[int, int] | None = None,
    moves: dict[int, tuple[int, int]] | None = None,
    detach: dict[int, bool] | None = None,
    attach_orphans: dict[int, tuple[int, int, int, int]] | None = None,
    raw_patches: Iterable[RawPatch] | None = None,
    durability: dict[int, float] | None = None,
) -> PatchResult:
    stack_counts = dict(stack_counts or {})
    moves = dict(moves or {})
    detach = dict(detach or {})
    attach_orphans = dict(attach_orphans or {})
    raw_patches = tuple(raw_patches or ())
    durability = {int(handle): float(value) for handle, value in (durability or {}).items()}
    if (
        new_money is None
        and not stack_counts
        and not moves
        and not detach
        and not attach_orphans
        and not raw_patches
        and not durability
    ):
        raise SaveError("Нет изменений для применения")
    if raw_patches and durability:
        raise SaveError("Нельзя совмещать raw patch с S2 durability в одном edit plan")
    conflict = set(moves) & set(detach)
    if conflict:
        h = next(iter(conflict))
        raise SaveError(f"Нельзя одновременно move и detach одного handle 0x{h:08X}")
    conflict = set(attach_orphans) & set(detach)
    if conflict:
        h = next(iter(conflict))
        raise SaveError(f"Нельзя одновременно attach и detach одного handle 0x{h:08X}")
    if new_money is not None and not (0 <= new_money <= 2_000_000_000):
        raise SaveError("Новая сумма должна быть от 0 до 2 000 000 000")

    stored, computed, ok = validate_crc(data)
    if not ok:
        raise SaveError(
            f"Отказ от правки: CRC32 исходника плохой ({stored:08x} != {computed:08x})"
        )

    raw_b = bytearray(decompress_save(data))
    original_raw = bytes(raw_b)
    old_money: int | None = None
    verified_money: int | None = None
    if new_money is not None:
        money_off, old_money = locate_money(raw_b)
        struct.pack_into("<I", raw_b, money_off, new_money)
        verified_money = new_money

    changed: list[tuple[int, int, int]] = []
    for handle, count in stack_counts.items():
        old, new = _patch_stack_in_raw(raw_b, int(handle), int(count))
        changed.append((int(handle), old, new))

    moved: list[tuple[int, int, int, int, int]] = []
    for handle, (x, y) in moves.items():
        ox, oy, nx, ny = _patch_move_in_raw(raw_b, int(handle), int(x), int(y))
        moved.append((int(handle), ox, oy, nx, ny))

    # Structural operations rebuild variable-length inventory arrays, so switch
    # to immutable bytes between each operation and re-parse every time.
    raw = bytes(raw_b)
    detached: list[tuple[int, bool]] = []
    for handle, deep in detach.items():
        raw = _detach_in_raw(raw, int(handle), bool(deep))
        detached.append((int(handle), bool(deep)))

    attached: list[tuple[int, int, int, int, int]] = []
    for handle, (x, y, w, h) in attach_orphans.items():
        raw = _attach_orphan_in_raw(raw, int(handle), int(x), int(y), int(w), int(h))
        attached.append((int(handle), int(x), int(y), int(w), int(h)))

    raw_b = bytearray(raw)
    for handle, condition in durability.items():
        _patch_s2_durability_in_raw(raw_b, handle, condition)
    for p in raw_patches:
        _apply_raw_patch(raw_b, p)

    expected_raw = bytes(raw_b)
    rebuilt, rebuild_decision = rebuild_compact(
        data, expected_raw, original_raw=original_raw
    )

    stored2, computed2, ok2 = validate_crc(rebuilt)
    if not ok2:
        raise SaveError(
            f"Внутренняя ошибка: CRC пересобранного файла неверен ({stored2:08x}/{computed2:08x})"
        )
    roundtrip = decompress_save(rebuilt)
    if roundtrip != expected_raw:
        raise SaveError("Round-trip проверка не прошла: распакованные данные отличаются")

    if new_money is not None:
        _, m = locate_money(roundtrip)
        if m != new_money:
            raise SaveError(f"После проверки деньги = {m}, ожидалось {new_money}")
        verified_money = m

    # Verify structural invariants after round-trip.
    verify_layout = locate_inventory_layout(roundtrip)
    verify_items = {it.handle: it for it in locate_inventory(roundtrip)}
    for handle, _old, new in changed:
        # A stack can also be detached in the same transaction; verify directly
        # from its object record instead of requiring it to remain visible in grid.
        _off, got_count, _weight, _kind = locate_object_record(roundtrip, handle)
        if got_count != new:
            raise SaveError(
                f"После round-trip stack 0x{handle:08X} = {got_count}, ожидалось {new}"
            )
    for handle, _ox, _oy, nx, ny in moved:
        got = verify_items.get(handle)
        if got is None or (got.x, got.y) != (nx, ny):
            raise SaveError(f"После round-trip move 0x{handle:08X} != {nx},{ny}")
    grid_handles = {c.handle for c in verify_layout.grid_cells}
    for handle, deep in detached:
        if handle in grid_handles:
            raise SaveError(f"После round-trip detached handle 0x{handle:08X} остался в grid")
        if deep and handle in verify_layout.owned_handles:
            raise SaveError(f"После round-trip deep-detached handle 0x{handle:08X} остался в owned list")
    for handle, x, y, w, h in attached:
        cells = {(c.x, c.y) for c in verify_layout.grid_cells if c.handle == handle}
        expected = {(x + dx, y + dy) for dy in range(h) for dx in range(w)}
        if cells != expected:
            raise SaveError(f"После round-trip attach 0x{handle:08X} cells={cells}, ожидалось {expected}")
    for handle, condition in durability.items():
        record_offset, _count, _weight, kind = locate_object_record(roundtrip, handle)
        checked_item = verify_items.get(handle)
        anchor: S2ConditionAnchor | S2WeaponConditionAnchor | None = None
        if kind == 1:
            anchor = read_s2_armor_condition(
                roundtrip,
                handle=handle,
                record_offset=record_offset,
                kind_code=kind,
            )
        elif kind == 0 and checked_item is not None:
            starts = _record_start_map(roundtrip, verify_layout.owned_handles)
            name_table = locate_s2_item_name_table(
                roundtrip,
                tuple(roundtrip[offset + 8 : offset + 11] for offset in starts.values()),
            )
            if name_table is not None:
                anchor = read_s2_weapon_condition(
                    roundtrip,
                    handle=handle,
                    record_offset=record_offset,
                    record_end=checked_item.record_end_guess,
                    kind_code=kind,
                    name_table=name_table,
                )
        if anchor is None or not math.isclose(
            anchor.value,
            condition,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise SaveError(
                f"После round-trip S2 condition 0x{handle:08X} "
                f"не совпал с {condition}"
            )

    return PatchResult(
        data=rebuilt,
        old_money=old_money,
        new_money=verified_money,
        changed_stacks=tuple(changed),
        moved_items=tuple(moved),
        detached_items=tuple(detached),
        attached_items=tuple(attached),
        raw_patches=raw_patches,
        rebuild_mode=rebuild_decision.mode,
        preserved_blocks=rebuild_decision.preserved_blocks,
        rebuilt_blocks=rebuild_decision.rebuilt_blocks,
        rebuild_reason=rebuild_decision.reason,
    )
