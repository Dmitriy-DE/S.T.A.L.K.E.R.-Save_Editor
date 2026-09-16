"""Small codecs for condition fields in original X-Ray inventory objects.

The original games serialize inventory-item condition twice: the authoritative
``STATE`` value is a little-endian float, while some ``UPDATE`` serializers
carry a quantized byte mirror.  This module discovers the mirror only when its
value agrees with the state field, so a writer never guesses from a nearby byte.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .xray_save import XRayObject


class ConditionCodecError(ValueError):
    """The requested object does not expose a safe condition anchor."""


CONDITION_FAMILIES = frozenset(
    {
        "weapon",
        "weapon_magazined",
        "weapon_shotgun",
        "weapon_wgl",
        "outfit",
    }
)
_UPDATE_CONDITION_RELATIVE_OFFSETS = (3, 4)
_Q8_STEP = 1.0 / 255.0
_SLOTS_COUNT = 14


@dataclass(frozen=True)
class ConditionAnchor:
    value: float
    state_offset: int
    update_offset: int | None
    client_offset: int | None
    storage: Literal["equipped", "inventory"] | None


def _state_condition_offset(raw: bytes, obj: XRayObject) -> tuple[int, float]:
    # Import lazily: xray_save owns the common bounds-checked reader and also
    # imports this module for the annotation/writer hooks.
    from .xray_save import _read_dynamic_visual_state, _Reader

    try:
        reader = _Reader(raw[obj.state_offset : obj.state_end], label=f"{obj.name} STATE")
        _read_dynamic_visual_state(reader, obj.version)
        if obj.version <= 52:
            raise ConditionCodecError("condition появился только после spawn version 52")
        offset = obj.state_offset + reader.pos
        if offset + 4 > obj.state_end:
            raise ConditionCodecError("STATE слишком короткий для condition f32")
        value = struct.unpack_from("<f", raw, offset)[0]
    except ConditionCodecError:
        raise
    except Exception as exc:
        raise ConditionCodecError(str(exc)) from exc
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ConditionCodecError(f"condition={value!r} вне диапазона 0…1")
    return offset, value


def _matching_update_offset(raw: bytes, obj: XRayObject, value: float) -> int | None:
    update = raw[obj.update_offset : obj.update_end]
    candidates: list[int] = []
    for relative in _UPDATE_CONDITION_RELATIVE_OFFSETS:
        if relative >= len(update):
            continue
        decoded = update[relative] / 255.0
        if abs(decoded - value) <= _Q8_STEP + 1e-6:
            candidates.append(obj.update_offset + relative)
    # More than one matching byte is ambiguous (especially for condition=0 or
    # 1), so preserve UPDATE rather than mutating an unproven field.
    return candidates[0] if len(candidates) == 1 else None


def _storage_from_place(value: int) -> Literal["equipped", "inventory"] | None:
    """Decode only source-defined inventory places that are safe to show."""

    place_type = value & 0x0F
    slot_id = (value >> 4) & 0x3F
    base_slot_id = (value >> 10) & 0x3F
    if place_type == 1:  # eItemPlaceSlot
        if slot_id >= _SLOTS_COUNT or base_slot_id >= _SLOTS_COUNT:
            return None
        return "equipped"
    if place_type in {2, 3}:  # eItemPlaceBelt / eItemPlaceRuck
        return "inventory"
    return None


def _matching_client_condition(
    raw: bytes,
    obj: XRayObject,
    value: float,
) -> tuple[int, Literal["equipped", "inventory"]] | None:
    """Find the client-data condition/place pair without assuming one offset."""

    if obj.client_data_offset is None or obj.client_data_end is None:
        return None
    start = obj.client_data_offset
    end = obj.client_data_end
    candidates: list[tuple[int, Literal["equipped", "inventory"]]] = []
    for offset in range(start + 2, end - 3):
        decoded = struct.unpack_from("<f", raw, offset)[0]
        if not math.isfinite(decoded) or abs(decoded - value) > 1e-6:
            continue
        place = struct.unpack_from("<H", raw, offset - 2)[0]
        storage = _storage_from_place(place)
        if storage is not None:
            candidates.append((offset, storage))
    return candidates[0] if len(candidates) == 1 else None


def read_condition_anchor(
    raw: bytes,
    obj: XRayObject,
    family: str,
) -> ConditionAnchor:
    """Read a target object's state condition and an optional safe q8 mirror."""

    if family.casefold() not in CONDITION_FAMILIES:
        raise ConditionCodecError(f"serializer family {family!r} не поддерживает condition")
    state_offset, value = _state_condition_offset(raw, obj)
    client_match = _matching_client_condition(raw, obj, value)
    return ConditionAnchor(
        value=value,
        state_offset=state_offset,
        update_offset=_matching_update_offset(raw, obj, value),
        client_offset=client_match[0] if client_match is not None else None,
        storage=client_match[1] if client_match is not None else None,
    )


def patch_condition(
    raw: bytearray,
    obj: XRayObject,
    family: str,
    value: float,
) -> ConditionAnchor:
    """Patch STATE and the already-proven UPDATE q8 mirror in-place."""

    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ConditionCodecError("condition должен быть конечным числом в диапазоне 0…1")
    anchor = read_condition_anchor(bytes(raw), obj, family)
    struct.pack_into("<f", raw, anchor.state_offset, value)
    if anchor.update_offset is not None:
        raw[anchor.update_offset] = min(255, max(0, math.floor(value * 255.0 + 0.5)))
    if anchor.client_offset is not None:
        struct.pack_into("<f", raw, anchor.client_offset, value)
    return anchor


__all__ = [
    "CONDITION_FAMILIES",
    "ConditionAnchor",
    "ConditionCodecError",
    "patch_condition",
    "read_condition_anchor",
]
