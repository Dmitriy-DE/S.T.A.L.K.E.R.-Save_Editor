from __future__ import annotations

import hashlib
import math
import struct
import zlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from editor.codec import CodecError
from editor.codec import decompress as codec_decompress
from editor.kraken_blocks import (
    CompactRebuildResult,
    KrakenBlocksError,
    RebuildMode,
    compact_rebuild_stream,
)

BLOCK_SIZE = 0x40000
UNCOMPRESSED_BLOCK_HEADER = b"\xCC\x06"
GRID_RECORD_SIZE = 8
GRID_WIDTH = 8
KNOWN_KIND_CODES = frozenset({0, 1, 2, 4, 5, 7, 8})
EDITABLE_STACK_KIND_CODES = frozenset({4, 5, 7, 8})

# Confirmed in the user's real saves. This is a campaign/player structure anchor,
# not a universal GSC guarantee; all mutating operations fail closed if it stops
# being unique.
MONEY_ANCHOR = bytes.fromhex(
    "0038010000000110cacfa848c8952149b51b9444000000000600000000060000"
)

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
    upgrades: tuple[str, ...] | None = None
    upgrades_editable: bool = False
    placement_type: Literal["slot", "belt", "ruck"] | None = None
    placement_slot: int | None = None
    placement_base_slot: int | None = None
    placement_editable: bool = False
    remove_editable: bool = False
    remove_reason: str | None = None

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
        2: "Уникальный/экипировка",
        4: "Расходник",
        5: "Патроны",
        7: "Гранаты/стак",
        8: "Разное",
    }.get(kind, f"Тип {kind}")


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
) -> tuple[str, ...] | None:
    """Locate the save-local item name table used by the S2 compact key.

    The currently observed S2 saves serialize a counted string table whose
    first entry is ``GunAK74_ST``.  The low two bytes of an inventory
    ``type_key`` are an index into that table.  This helper exposes only that
    save-local display metadata; it does not turn the entry into a public SID
    and does not provide a constructor/writer.
    """

    indexes: list[int] = []
    for type_key in type_keys:
        if len(type_key) != 3:
            continue
        indexes.append(type_key[1] | (type_key[2] << 8))
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
        if names is not None and names[0] == "GunAK74_ST" and (
            not indexes or any(index < len(names) for index in indexes)
        ):
            return names
        search_from = name_offset + 1


def _s2_display_name(
    name_table: tuple[str, ...] | None,
    type_key: bytes,
) -> str | None:
    if name_table is None or len(type_key) != 3:
        return None
    index = type_key[1] | (type_key[2] << 8)
    if not (0 <= index < len(name_table)):
        return None
    return name_table[index] or None


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
        editable = count > 1 and kind in EDITABLE_STACK_KIND_CODES and handle not in unresolved
        fingerprint = raw[rec_off + 4 : rec_off + 18].hex()
        # The first byte remains an opaque S2 serialization discriminator. The
        # lower two bytes resolve through the save-local name table when the
        # table is present; neither field is claimed to be a public SID/hash.
        type_key = raw[rec_off + 8 : rec_off + 11].hex()
        display_name = _s2_display_name(name_table, raw[rec_off + 8 : rec_off + 11])
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
                category=_category_name(kind),
                record_offset=rec_off,
                record_end_guess=ends.get(handle, min(len(raw), rec_off + 512)),
                fingerprint=fingerprint,
                type_key=type_key,
                editable_count=editable,
                display_name=display_name,
            )
        )
    items.sort(key=lambda it: (it.y, it.x, it.handle))
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
    """Rebuild a save while preserving only proven source Kraken blocks.

    This function never encodes Kraken.  It copies safe original blocks and
    emits changed/dependent blocks in the known stored ``CC06`` form; a
    changed raw length or unsupported framing produces a valid full stored
    rebuild instead.
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


def scalar_candidates(raw: bytes, handle: int, limit: int = 1024) -> list[dict[str, object]]:
    """Heuristic lab candidates, intentionally not labelled as durability.

    Returns aligned/unaligned f32 values 0..1 and bytes 0..100 in the selected
    record window. This is for differential research and manual testing only.
    """
    base, blob = record_hex(raw, handle, limit)
    out: list[dict[str, object]] = []
    for rel in range(0, max(0, len(blob) - 4)):
        f = struct.unpack_from("<f", blob, rel)[0]
        if math.isfinite(f) and 0.0 <= f <= 1.0:
            out.append({"offset": base + rel, "rel": rel, "kind": "f32", "value": f})
    for rel, b in enumerate(blob):
        if b <= 100:
            out.append({"offset": base + rel, "rel": rel, "kind": "u8", "value": b})
    return out


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
) -> PatchResult:
    stack_counts = dict(stack_counts or {})
    moves = dict(moves or {})
    detach = dict(detach or {})
    attach_orphans = dict(attach_orphans or {})
    raw_patches = tuple(raw_patches or ())
    if new_money is None and not stack_counts and not moves and not detach and not attach_orphans and not raw_patches:
        raise SaveError("Нет изменений для применения")
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


def patch_money(data: bytes, new_money: int) -> tuple[bytes, int, int]:
    result = patch_save(data, new_money=new_money)
    assert result.old_money is not None and result.new_money is not None
    return result.data, result.old_money, result.new_money


def patch_stack_count(data: bytes, handle: int, new_count: int) -> tuple[bytes, int, int]:
    result = patch_save(data, stack_counts={handle: new_count})
    _h, old, new = result.changed_stacks[0]
    return result.data, old, new
