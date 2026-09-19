"""Immutable staging helpers for individual and bulk equipment repair."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from .equipment import EquipmentItem

RepairFilter = Literal[
    "all",
    "weapon",
    "armor",
    "helmet",
    "equipped",
    "inventory",
    "damaged",
]


@dataclass(frozen=True)
class RepairSkip:
    """One requested item that was deliberately not staged."""

    handle: int
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"handle": self.handle, "reason": self.reason}


@dataclass(frozen=True)
class RepairStageResult:
    """The immutable staged changes and explainable skipped rows."""

    changes: tuple[tuple[int, float], ...]
    skipped: tuple[RepairSkip, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "changes": [[handle, value] for handle, value in self.changes],
            "skipped": [item.as_dict() for item in self.skipped],
        }


def _normalise_percentage(value: float) -> float:
    try:
        percentage = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("repair percentage must be finite and in the range 0…100") from exc
    if not math.isfinite(percentage) or not 0.0 <= percentage <= 100.0:
        raise ValueError("repair percentage must be finite and in the range 0…100")
    return percentage / 100.0


def _dedupe_handles(handles: Iterable[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    result: list[int] = []
    for handle in handles:
        normalised = int(handle)
        if normalised not in seen:
            seen.add(normalised)
            result.append(normalised)
    return tuple(result)


def stage_repair(
    items: Iterable[EquipmentItem],
    handles: Iterable[int],
    percentage: float,
) -> RepairStageResult:
    """Stage one target value for exact handles without changing source data."""

    target = _normalise_percentage(percentage)
    by_handle = {item.handle: item for item in items}
    changes: list[tuple[int, float]] = []
    skipped: list[RepairSkip] = []
    for handle in _dedupe_handles(handles):
        item = by_handle.get(handle)
        if item is None:
            skipped.append(RepairSkip(handle, "not found in the current snapshot"))
            continue
        if item.category == "other":
            skipped.append(
                RepairSkip(
                    handle,
                    "not an equipment category; condition writer is not confirmed",
                )
            )
            continue
        if item.condition is None:
            skipped.append(
                RepairSkip(handle, "condition is missing from the current save")
            )
            continue
        if not item.durability_editable:
            reason = item.durability.reason or "durability writer is not available"
            skipped.append(
                RepairSkip(
                    handle,
                    f"read-only ({item.durability.maturity}): {reason}",
                )
            )
            continue
        if math.isclose(item.condition, target, rel_tol=0.0, abs_tol=1e-6):
            skipped.append(RepairSkip(handle, "no-op: item already has this durability"))
            continue
        changes.append((handle, target))
    return RepairStageResult(tuple(changes), tuple(skipped))


def _matches_filter(item: EquipmentItem, filter_name: RepairFilter) -> bool:
    if filter_name == "all":
        return item.category != "other"
    if filter_name == "damaged":
        return item.category != "other" and item.damaged
    if filter_name in {"weapon", "armor", "helmet"}:
        return item.category == filter_name
    if filter_name == "equipped":
        return item.location == "equipped" and item.category != "other"
    if filter_name == "inventory":
        return item.location == "inventory" and item.category != "other"
    raise ValueError(f"unknown repair filter: {filter_name!r}")


def stage_bulk_repair(
    items: Iterable[EquipmentItem],
    filter_name: RepairFilter,
    percentage: float,
) -> RepairStageResult:
    """Select a product filter and stage only safe, changed equipment rows."""

    snapshot = tuple(items)
    handles = (
        item.handle
        for item in snapshot
        if _matches_filter(item, filter_name)
    )
    return stage_repair(snapshot, handles, percentage)


__all__ = [
    "RepairFilter",
    "RepairSkip",
    "RepairStageResult",
    "stage_bulk_repair",
    "stage_repair",
]
