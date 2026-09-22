"""Read-only, reproducible evidence reports for equipment format research."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from save_format import SaveError

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


class InputChangedError(ValueError):
    """An input was not stable for the duration of read-only analysis."""


@dataclass(frozen=True)
class EquipmentCorpusSample:
    """An anonymized, aggregate-only observation for a corpus report."""

    sample_id: str
    sha256: str
    packed_size: int
    raw_size: int
    release_id: str
    category_counts: tuple[tuple[str, int], ...]
    actor_owned_count: int
    grid_count: int
    equipped_count: int
    condition_anchor_status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "sample_id": self.sample_id,
            "sha256": self.sha256,
            "packed_size": self.packed_size,
            "raw_size": self.raw_size,
            "release_id": self.release_id,
            "category_counts": dict(self.category_counts),
            "actor_owned_count": self.actor_owned_count,
            "grid_count": self.grid_count,
            "equipped_count": self.equipped_count,
            "condition_anchor_status": self.condition_anchor_status,
        }


@dataclass(frozen=True)
class EquipmentCorpusReport:
    """A path-free, byte-free read-only S2 equipment corpus report."""

    file_count: int
    accepted_count: int
    rejected_count: int
    release_id: str | None
    category_totals: tuple[tuple[str, int], ...]
    actor_owned_count: int
    grid_count: int
    equipped_count: int
    condition_anchor_status: str
    samples: tuple[EquipmentCorpusSample, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_count": self.file_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "release_id": self.release_id,
            "category_totals": dict(self.category_totals),
            "actor_owned_count": self.actor_owned_count,
            "grid_count": self.grid_count,
            "equipped_count": self.equipped_count,
            "condition_anchor_status": self.condition_anchor_status,
            "samples": [sample.as_dict() for sample in self.samples],
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


@dataclass(frozen=True)
class _InputSnapshot:
    path: Path
    data: bytes
    size: int
    mtime_ns: int


def _snapshot(path: Path) -> _InputSnapshot:
    """Capture bytes and metadata, refusing a file already changing."""

    try:
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise ValueError(f"cannot read corpus input: {exc}") from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(data) != after.st_size
    ):
        raise InputChangedError("input file changed during analysis")
    return _InputSnapshot(path, data, after.st_size, after.st_mtime_ns)


def _assert_unchanged(snapshot: _InputSnapshot) -> None:
    try:
        stat = snapshot.path.stat()
        current = snapshot.path.read_bytes()
    except OSError as exc:
        raise InputChangedError("input file changed during analysis") from exc
    if (
        stat.st_size != snapshot.size
        or stat.st_mtime_ns != snapshot.mtime_ns
        or current != snapshot.data
    ):
        raise InputChangedError("input file changed during analysis")


def _corpus_sample(snapshot: _InputSnapshot, sample_number: int) -> EquipmentCorpusSample:
    """Analyze one stable input without retaining its path or raw bytes."""

    try:
        format_ = detect_or_raise(snapshot.data, display_name="corpus input")
        info = format_.inspect(snapshot.data)
        rows: tuple[EquipmentItem, ...] = equipment_items(
            info.inventory,
            release_id=format_.release_id,
        )
    finally:
        _assert_unchanged(snapshot)
    condition_rows = sum(row.condition is not None for row in rows)
    return EquipmentCorpusSample(
        sample_id=f"sample-{sample_number:03d}",
        sha256=hashlib.sha256(snapshot.data).hexdigest(),
        packed_size=info.packed_size,
        raw_size=info.unpacked_size,
        release_id=format_.release_id,
        category_counts=_count(tuple(row.category for row in rows)),
        actor_owned_count=len(info.owned_handles),
        grid_count=info.grid_cell_count,
        equipped_count=sum(row.location == "equipped" for row in rows),
        condition_anchor_status="observed" if condition_rows else "not_observed",
    )


def analyze_equipment_corpus(
    input_root: Path,
    *,
    expected_release_id: str | None = None,
) -> EquipmentCorpusReport:
    """Read a corpus recursively and return anonymized aggregate observations.

    Invalid files are counted as rejected. Any file that changes during the
    scan aborts the run so the report cannot describe a moving target.
    """

    root = Path(input_root).expanduser()
    if not root.is_dir():
        raise ValueError("input root must be an existing directory")
    paths = tuple(sorted(path for path in root.rglob("*") if path.is_file()))
    accepted: list[EquipmentCorpusSample] = []
    rejected = 0
    for path in paths:
        snapshot = _snapshot(path)
        try:
            sample = _corpus_sample(snapshot, len(accepted) + 1)
            if expected_release_id is not None and sample.release_id != expected_release_id:
                rejected += 1
                continue
        except InputChangedError:
            raise
        except (OSError, SaveError, ValueError):
            rejected += 1
            continue
        accepted.append(sample)

    releases = {sample.release_id for sample in accepted}
    category_totals = Counter(
        category
        for sample in accepted
        for category, count in sample.category_counts
        for _ in range(count)
    )
    condition_status = (
        "observed"
        if any(sample.condition_anchor_status == "observed" for sample in accepted)
        else "not_observed"
    )
    return EquipmentCorpusReport(
        file_count=len(paths),
        accepted_count=len(accepted),
        rejected_count=rejected,
        release_id=next(iter(releases)) if len(releases) == 1 else None,
        category_totals=tuple(sorted(category_totals.items())),
        actor_owned_count=sum(sample.actor_owned_count for sample in accepted),
        grid_count=sum(sample.grid_count for sample in accepted),
        equipped_count=sum(sample.equipped_count for sample in accepted),
        condition_anchor_status=condition_status,
        samples=tuple(accepted),
    )


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
    "EquipmentCorpusReport",
    "EquipmentCorpusSample",
    "EquipmentResearchReport",
    "EquipmentSample",
    "InputChangedError",
    "analyze_equipment_corpus",
    "analyze_equipment_samples",
]
