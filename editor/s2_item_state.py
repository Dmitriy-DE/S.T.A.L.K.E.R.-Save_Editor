"""Narrow, source-backed codecs for S.T.A.L.K.E.R. 2 item state."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass

S2_ARMOR_KIND_CODE = 1
S2_WEAPON_KIND_CODE = 0
S2_EQUIPMENT_KIND_CODES = frozenset({0, 1, 2})
S2_ARMOR_NESTED_RELATIVE_OFFSET = 0x23
S2_ARMOR_CONDITION_RELATIVE_OFFSET = 4
S2_WEAPON_SCAN_LIMIT = 0x800
S2_WEAPON_PRIMARY_STATE_LIMIT = 0x400
S2_WEAPON_MAX_UPGRADES = 64
S2_WEAPON_MIN_UPGRADES = 2


class S2ItemStateError(ValueError):
    """The requested S2 item state does not expose a safe field."""


@dataclass(frozen=True)
class S2ConditionAnchor:
    """One confirmed S2 armor condition field in the decompressed payload."""

    handle: int
    record_offset: int
    nested_offset: int
    value_offset: int
    value: float


@dataclass(frozen=True)
class S2WeaponConditionAnchor:
    """Observed S2 weapon condition plus its read-only attachment vectors.

    The condition is the only scalar this codec can mutate.  The module and
    upgrade vectors are returned as evidence for the UI, but their IDs are
    deliberately not exposed as a writer until a game load/re-save sample
    proves the surrounding serializer contract.
    """

    handle: int
    record_offset: int
    value_offset: int
    value: float
    upgrades_offset: int
    upgrades_count: int
    upgrades_end: int
    modules: tuple[str, ...]
    upgrades: tuple[str, ...]


def _packed_handle(handle: int) -> bytes | None:
    if not 0 <= handle <= 0xFFFFFFFF:
        return None
    return struct.pack("<I", handle)


def has_s2_equipment_shape(
    raw: bytes | bytearray,
    *,
    handle: int,
    record_offset: int,
    kind_code: int,
) -> bool:
    """Return whether an owned non-grid record has the observed S2 shape."""

    if kind_code not in S2_EQUIPMENT_KIND_CODES:
        return False
    if record_offset < 0 or record_offset + 4 > len(raw):
        return False
    nested_offset = record_offset + S2_ARMOR_NESTED_RELATIVE_OFFSET
    if nested_offset + 4 > len(raw):
        return False
    packed_handle = _packed_handle(handle)
    if packed_handle is None:
        return False
    return (
        raw[record_offset : record_offset + 4] == packed_handle
        and raw[nested_offset : nested_offset + 4] == packed_handle
    )


def _read_anchor(
    raw: bytes | bytearray,
    *,
    handle: int,
    record_offset: int,
    kind_code: int,
) -> S2ConditionAnchor | None:
    if kind_code != S2_ARMOR_KIND_CODE:
        return None
    if record_offset < 0 or record_offset + 4 > len(raw):
        return None
    packed_handle = _packed_handle(handle)
    if packed_handle is None:
        return None
    if raw[record_offset : record_offset + 4] != packed_handle:
        return None
    nested_offset = record_offset + S2_ARMOR_NESTED_RELATIVE_OFFSET
    value_offset = nested_offset + S2_ARMOR_CONDITION_RELATIVE_OFFSET
    if value_offset + 4 > len(raw):
        return None
    if raw[nested_offset : nested_offset + 4] != packed_handle:
        return None
    value = struct.unpack_from("<f", raw, value_offset)[0]
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        return None
    return S2ConditionAnchor(
        handle=handle,
        record_offset=record_offset,
        nested_offset=nested_offset,
        value_offset=value_offset,
        value=value,
    )


def read_s2_armor_condition(
    raw: bytes,
    *,
    handle: int,
    record_offset: int,
    kind_code: int,
) -> S2ConditionAnchor | None:
    """Read the exact condition anchor for a confirmed S2 armor record."""

    return _read_anchor(
        raw,
        handle=handle,
        record_offset=record_offset,
        kind_code=kind_code,
    )


def patch_s2_armor_condition(
    raw: bytearray,
    *,
    handle: int,
    record_offset: int,
    kind_code: int,
    value: float,
) -> S2ConditionAnchor:
    """Patch only the confirmed four-byte S2 armor condition field."""

    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise S2ItemStateError("S2 armor condition must be finite and in the range 0…1")
    anchor = _read_anchor(
        raw,
        handle=handle,
        record_offset=record_offset,
        kind_code=kind_code,
    )
    if anchor is None:
        raise S2ItemStateError(
            f"S2 armor condition anchor is not confirmed for handle 0x{handle:08X}"
        )
    struct.pack_into("<f", raw, anchor.value_offset, value)
    return S2ConditionAnchor(
        handle=anchor.handle,
        record_offset=anchor.record_offset,
        nested_offset=anchor.nested_offset,
        value_offset=anchor.value_offset,
        value=value,
    )


def _name_for_key(key: bytes, name_table: Sequence[str]) -> str | None:
    if len(key) != 3:
        return None
    index = key[1] | (key[2] << 8)
    if not 0 <= index < len(name_table):
        return None
    name = str(name_table[index]).strip()
    return name or None


def _upgrade_vector(
    raw: bytes | bytearray,
    *,
    offset: int,
    limit: int,
    name_table: Sequence[str],
) -> tuple[int, tuple[str, ...], int] | None:
    if offset < 0 or offset + 2 > limit:
        return None
    count = struct.unpack_from("<H", raw, offset)[0]
    if not 1 <= count <= S2_WEAPON_MAX_UPGRADES:
        return None
    values_start = offset + 2
    values_end = values_start + count * 3
    if values_end > limit:
        return None
    values: list[str] = []
    for index in range(count):
        name = _name_for_key(
            bytes(raw[values_start + index * 3 : values_start + index * 3 + 3]),
            name_table,
        )
        if name is None or "_upgrade_" not in name.casefold():
            return None
        values.append(name)
    return count, tuple(values), values_end


def _is_direct_module_name(name: str) -> bool:
    lowered = name.casefold()
    if "_upgrade_" in lowered:
        return False
    return lowered.startswith(("en_", "hp_", "ru_", "toprail")) or "_mag" in lowered


def _direct_modules(
    raw: bytes | bytearray,
    *,
    value_offset: int,
    record_start: int,
    name_table: Sequence[str],
) -> tuple[str, ...]:
    values: list[str] = []
    offset = value_offset - 3
    # A direct attachment run is immediately before the condition scalar in
    # all currently observed Kharod/Lavina records.  Keep the look-back local
    # so unrelated embedded actor records cannot be misclassified as modules.
    while offset >= record_start + 0x30:
        name = _name_for_key(bytes(raw[offset : offset + 3]), name_table)
        if name is None or not _is_direct_module_name(name):
            break
        values.append(name)
        offset -= 3
    values.reverse()
    return tuple(values)


def read_s2_weapon_condition(
    raw: bytes,
    *,
    handle: int,
    record_offset: int,
    record_end: int | None,
    kind_code: int,
    name_table: Sequence[str],
) -> S2WeaponConditionAnchor | None:
    """Read the currently observed S2 weapon condition/vector shape.

    S2 stores compact three-byte name keys around this state.  A candidate is
    accepted only when the following counted vector resolves entirely to
    ``*_Upgrade_*`` names.  A scalar in the 0…1 range by itself is never
    enough, which keeps devices such as NVG/binocular records read-only.
    """

    if kind_code != S2_WEAPON_KIND_CODE:
        return None
    if record_offset < 0 or record_offset + 4 > len(raw):
        return None
    packed_handle = _packed_handle(handle)
    if packed_handle is None or raw[record_offset : record_offset + 4] != packed_handle:
        return None
    limit = min(
        len(raw),
        record_offset + S2_WEAPON_SCAN_LIMIT,
        len(raw) if record_end is None else max(record_offset, record_end),
    )
    if limit <= record_offset + 0x30:
        return None
    candidates: list[S2WeaponConditionAnchor] = []
    for value_offset in range(record_offset + 0x30, limit - 6):
        value = struct.unpack_from("<f", raw, value_offset)[0]
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            continue
        vector = _upgrade_vector(
            raw,
            offset=value_offset + 4,
            limit=limit,
            name_table=name_table,
        )
        if vector is None:
            continue
        count, upgrades, upgrades_end = vector
        if count < S2_WEAPON_MIN_UPGRADES:
            continue
        modules = _direct_modules(
            raw,
            value_offset=value_offset,
            record_start=record_offset,
            name_table=name_table,
        )
        if not modules:
            # The same weapon record contains a second, available-upgrades
            # vector after the installed vector.  It has the same shape but
            # no direct attachment run; requiring that run keeps the reader
            # anchored to the observed current-item state.
            continue
        family = upgrades[0].split("_Upgrade_", 1)[0].casefold()
        if not any(module.casefold().startswith(family + "_") for module in modules):
            # Keep an unrelated compact-key run from turning a random 0…1
            # float into a weapon condition anchor.
            continue
        candidates.append(
            S2WeaponConditionAnchor(
                handle=handle,
                record_offset=record_offset,
                value_offset=value_offset,
                value=value,
                upgrades_offset=value_offset + 4,
                upgrades_count=count,
                upgrades_end=upgrades_end,
                modules=modules,
                upgrades=upgrades,
            )
        )
    if len(candidates) == 1:
        return candidates[0]

    # A broad record-end guess can contain a second serialized weapon snapshot
    # (for example, the currently held Skif pistol followed by an embedded
    # Lavina state).  The current-item state is the only accepted candidate in
    # the primary prefix observed across the supplied corpus.  Keep ambiguity
    # inside that prefix read-only; choose the single early candidate only when
    # every competing candidate is outside it.
    primary = tuple(
        candidate
        for candidate in candidates
        if candidate.value_offset - record_offset < S2_WEAPON_PRIMARY_STATE_LIMIT
    )
    if len(primary) == 1:
        return primary[0]
    return None


def patch_s2_weapon_condition(
    raw: bytearray,
    *,
    handle: int,
    record_offset: int,
    record_end: int | None,
    kind_code: int,
    name_table: Sequence[str],
    value: float,
) -> S2WeaponConditionAnchor:
    """Patch only the observed four-byte S2 weapon condition scalar."""

    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise S2ItemStateError("S2 weapon condition must be finite and in the range 0…1")
    anchor = read_s2_weapon_condition(
        bytes(raw),
        handle=handle,
        record_offset=record_offset,
        record_end=record_end,
        kind_code=kind_code,
        name_table=name_table,
    )
    if anchor is None:
        raise S2ItemStateError(
            f"S2 weapon condition anchor is not confirmed for handle 0x{handle:08X}"
        )
    struct.pack_into("<f", raw, anchor.value_offset, value)
    return S2WeaponConditionAnchor(
        handle=anchor.handle,
        record_offset=anchor.record_offset,
        value_offset=anchor.value_offset,
        value=value,
        upgrades_offset=anchor.upgrades_offset,
        upgrades_count=anchor.upgrades_count,
        upgrades_end=anchor.upgrades_end,
        modules=anchor.modules,
        upgrades=anchor.upgrades,
    )


__all__ = [
    "S2_ARMOR_CONDITION_RELATIVE_OFFSET",
    "S2_ARMOR_KIND_CODE",
    "S2_ARMOR_NESTED_RELATIVE_OFFSET",
    "S2_EQUIPMENT_KIND_CODES",
    "S2_WEAPON_KIND_CODE",
    "S2_WEAPON_MAX_UPGRADES",
    "S2_WEAPON_MIN_UPGRADES",
    "S2_WEAPON_PRIMARY_STATE_LIMIT",
    "S2_WEAPON_SCAN_LIMIT",
    "S2ConditionAnchor",
    "S2ItemStateError",
    "S2WeaponConditionAnchor",
    "has_s2_equipment_shape",
    "patch_s2_armor_condition",
    "patch_s2_weapon_condition",
    "read_s2_armor_condition",
    "read_s2_weapon_condition",
]
