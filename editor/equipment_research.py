"""Read-only, reproducible evidence reports for equipment format research."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .equipment import EquipmentItem, equipment_items, equipment_support_for_release
from .formats import detect_or_raise


@dataclass(frozen=True)
class EquipmentSample:
    """One immutable observation from one explicitly selected save."""

    path: str
    sha256: str
    format_id: str
    category_counts: tuple[tuple[str, int], ...]
    location_counts: tuple[tuple[str, int], ...]
    condition_rows: int
    writable_condition_rows: int

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "format_id": self.format_id,
            "category_counts": dict(self.category_counts),
            "location_counts": dict(self.location_counts),
            "condition_rows": self.condition_rows,
            "writable_condition_rows": self.writable_condition_rows,
        }


@dataclass(frozen=True)
class EquipmentResearchReport:
    """A JSON-safe report that never includes or changes save bytes."""

    release_id: str
    maturity: str
    samples: tuple[EquipmentSample, ...]
    blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "maturity": self.maturity,
            "samples": [sample.as_dict() for sample in self.samples],
            "blockers": list(self.blockers),
        }


def _count(values: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(Counter(values).items()))


def _sample(path: Path) -> tuple[EquipmentSample, str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read sample {path}: {exc}") from exc
    format_ = detect_or_raise(data, display_name=str(path))
    info = format_.inspect(data)
    rows: tuple[EquipmentItem, ...] = equipment_items(
        info.inventory,
        release_id=format_.release_id,
    )
    sample = EquipmentSample(
        path=str(path),
        sha256=hashlib.sha256(data).hexdigest(),
        format_id=format_.id,
        category_counts=_count(tuple(row.category for row in rows)),
        location_counts=_count(tuple(row.location for row in rows)),
        condition_rows=sum(row.condition is not None for row in rows),
        writable_condition_rows=sum(row.durability_editable for row in rows),
    )
    return sample, format_.release_id


def analyze_equipment_samples(
    paths: tuple[Path, ...] | list[Path],
    *,
    expected_release_id: str | None = None,
) -> EquipmentResearchReport:
    """Inspect explicit samples and return evidence without writing anything."""

    if not paths:
        raise ValueError("at least one sample path is required")
    samples: list[EquipmentSample] = []
    release_id: str | None = None
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        sample, detected_release_id = _sample(path)
        if expected_release_id is not None and detected_release_id != expected_release_id:
            raise ValueError(
                f"expected release {expected_release_id!r}, detected {detected_release_id!r} in {path}"
            )
        if release_id is None:
            release_id = detected_release_id
        elif detected_release_id != release_id:
            raise ValueError(
                f"mixed release samples: {release_id!r} and {detected_release_id!r}"
            )
        samples.append(sample)

    assert release_id is not None
    support = equipment_support_for_release(release_id)
    blockers: list[str] = []
    if release_id == "stalker2":
        if len(samples) < 3:
            blockers.append(
                "Need at least three controlled same-handle S2 samples covering weapon, armor, and helmet states."
            )
        blockers.append(
            "Game load/re-save evidence is required before promoting the S2 durability writer from experimental to verified."
        )
        observed = {category for sample in samples for category, _count_value in sample.category_counts}
        missing = {"weapon", "armor", "helmet"} - observed
        if missing:
            blockers.append(
                "Controlled S2 categories not observed: " + ", ".join(sorted(missing)) + "."
            )
    elif release_id.endswith("-ee"):
        blockers.append("Enhanced Edition parser and equipment format sample are not accepted.")
    else:
        blockers.append(
            "Structural round-trip is not game load/re-save evidence for this original X-Ray release."
        )
    if support.durability.reason and support.durability.maturity in {"research", "unsupported"}:
        blockers.append(support.durability.reason)
    return EquipmentResearchReport(
        release_id=release_id,
        maturity=support.durability.maturity,
        samples=tuple(samples),
        blockers=tuple(dict.fromkeys(blockers)),
    )


__all__ = [
    "EquipmentResearchReport",
    "EquipmentSample",
    "analyze_equipment_samples",
]
