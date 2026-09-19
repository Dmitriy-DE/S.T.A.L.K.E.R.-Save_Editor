"""Narrow, source-backed codecs for S.T.A.L.K.E.R. 2 item state."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

S2_ARMOR_KIND_CODE = 1
S2_EQUIPMENT_KIND_CODES = frozenset({0, 1, 2})
S2_ARMOR_NESTED_RELATIVE_OFFSET = 0x23
S2_ARMOR_CONDITION_RELATIVE_OFFSET = 4


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


__all__ = [
    "S2_ARMOR_CONDITION_RELATIVE_OFFSET",
    "S2_ARMOR_KIND_CODE",
    "S2_ARMOR_NESTED_RELATIVE_OFFSET",
    "S2_EQUIPMENT_KIND_CODES",
    "S2ConditionAnchor",
    "S2ItemStateError",
    "has_s2_equipment_shape",
    "patch_s2_armor_condition",
    "read_s2_armor_condition",
]
