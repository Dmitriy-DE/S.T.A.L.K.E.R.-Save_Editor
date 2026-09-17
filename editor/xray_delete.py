"""Reference-safety preflight for structural X-Ray object deletion.

The original trilogy's save registry exposes a proven ``parent_id`` edge for
each parsed object.  A delete is safe to serialize only when the selected
object is actor-owned, is not explicitly equipped, and has no parsed registry
children.  This module deliberately reports a conservative decision; it does
not infer references from opaque state bytes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .xray_save import XRayObject, XRaySave


@dataclass(frozen=True)
class XRayDeleteAnalysis:
    """Read-only result of the known-reference deletion checks."""

    object_id: int
    allowed: bool
    blockers: tuple[str, ...]
    dependent_ids: tuple[int, ...]

    @property
    def message(self) -> str:
        """Return a stable human-readable explanation for the UI/writer."""

        if self.blockers:
            return "; ".join(self.blockers)
        return "object is an actor-owned leaf inventory record"


def analyze_xray_delete(parsed: XRaySave, object_id: int) -> XRayDeleteAnalysis:
    """Check whether a parsed object may be structurally detached.

    Missing objects are returned as a blocked analysis instead of being
    mistaken for an empty registry slot.  ``storage is None`` remains
    compatible with the legacy fixture/writer path: it means placement was
    not decoded, not that the object is known to be equipped.
    """

    target = next(
        (obj for obj in parsed.objects if obj.object_id == object_id),
        None,
    )
    if target is None:
        return XRayDeleteAnalysis(
            object_id=object_id,
            allowed=False,
            blockers=("target object is unresolved or missing",),
            dependent_ids=(),
        )

    dependent_ids = tuple(
        sorted(
            obj.object_id
            for obj in parsed.objects
            if obj.object_id != target.object_id
            and obj.parent_id == target.object_id
        )
    )
    return _analysis_for_target(parsed, target, dependent_ids)


def analyze_xray_deletes(
    parsed: XRaySave,
    object_ids: Iterable[int],
) -> dict[int, XRayDeleteAnalysis]:
    """Analyze several targets with one pass over the object registry."""

    requested = tuple(dict.fromkeys(int(object_id) for object_id in object_ids))
    target_by_id = {
        obj.object_id: obj
        for obj in parsed.objects
        if obj.object_id in requested
    }
    dependents: dict[int, list[int]] = {object_id: [] for object_id in requested}
    for obj in parsed.objects:
        children = dependents.get(obj.parent_id)
        if children is not None and obj.object_id != obj.parent_id:
            children.append(obj.object_id)

    analyses: dict[int, XRayDeleteAnalysis] = {}
    for object_id in requested:
        target = target_by_id.get(object_id)
        if target is None:
            analyses[object_id] = XRayDeleteAnalysis(
                object_id=object_id,
                allowed=False,
                blockers=("target object is unresolved or missing",),
                dependent_ids=(),
            )
            continue
        analyses[object_id] = _analysis_for_target(
            parsed,
            target,
            tuple(sorted(dependents[object_id])),
        )
    return analyses


def _analysis_for_target(
    parsed: XRaySave,
    target: XRayObject,
    dependent_ids: tuple[int, ...],
) -> XRayDeleteAnalysis:
    """Build one decision after target/dependent lookup is complete."""

    blockers: list[str] = []
    if target.object_id == parsed.actor_id:
        blockers.append("target is actor")
    elif target.parent_id != parsed.actor_id:
        blockers.append("object is not actor-owned")
    if target.storage == "equipped":
        blockers.append("equipped object cannot be deleted")
    if target.object_id in parsed.unresolved_handles:
        blockers.append("object is unresolved")
    if dependent_ids:
        formatted = ", ".join(f"0x{value:04X}" for value in dependent_ids)
        blockers.append(f"object has dependent registry children: {formatted}")

    return XRayDeleteAnalysis(
        object_id=target.object_id,
        allowed=not blockers,
        blockers=tuple(blockers),
        dependent_ids=dependent_ids,
    )


__all__ = ["XRayDeleteAnalysis", "analyze_xray_delete", "analyze_xray_deletes"]
