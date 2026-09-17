"""Read-only evidence helpers for S.T.A.L.K.E.R. 2 save-key research.

The three-byte value exposed by the S2 parser is intentionally treated as an
opaque save-local key.  This module compares that value across caller-supplied
save samples; it never turns a public prototype SID into a save key and never
modifies a save.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from save_format import SaveInfo, inspect_save

MappingStatus = Literal["unconfirmed"]


@dataclass(frozen=True)
class S2ItemObservation:
    """One parsed inventory item in one save sample."""

    sample: str
    sha256: str
    handle: int
    type_key: str
    category: str
    count: int | None


@dataclass(frozen=True)
class S2SampleSummary:
    """Privacy-safe summary of one input save."""

    sample: str
    sha256: str
    item_count: int
    owned_count: int
    grid_cell_count: int
    unique_type_key_count: int


@dataclass(frozen=True)
class S2HandleComparison:
    """Observations for one handle that appears in multiple samples."""

    handle: int
    observations: tuple[S2ItemObservation, ...]
    stable_type_key: bool


@dataclass(frozen=True)
class S2MappingReport:
    """Deterministic report that deliberately cannot confirm a SID mapping."""

    samples: tuple[S2SampleSummary, ...]
    shared_handles: tuple[S2HandleComparison, ...]
    reused_type_keys: tuple[tuple[str, tuple[int, ...]], ...]
    mapping_status: MappingStatus = "unconfirmed"
    mapping_reason: str = (
        "Нет SID-помеченной контролируемой пары сохранений; compact type_key "
        "остаётся неприсвоенным save-ключом"
    )

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe output without raw bytes or filesystem paths."""

        return {
            "mapping_status": self.mapping_status,
            "mapping_reason": self.mapping_reason,
            "sample_count": self.sample_count,
            "samples": [
                {
                    "sample": sample.sample,
                    "sha256": sample.sha256,
                    "item_count": sample.item_count,
                    "owned_count": sample.owned_count,
                    "grid_cell_count": sample.grid_cell_count,
                    "unique_type_key_count": sample.unique_type_key_count,
                }
                for sample in self.samples
            ],
            "shared_handles": [
                {
                    "handle": f"0x{comparison.handle:08X}",
                    "stable_type_key": comparison.stable_type_key,
                    "observations": [
                        {
                            "sample": observation.sample,
                            "sha256": observation.sha256,
                            "type_key": observation.type_key,
                            "category": observation.category,
                            "count": observation.count,
                        }
                        for observation in comparison.observations
                    ],
                }
                for comparison in self.shared_handles
            ],
            "reused_type_keys": [
                {
                    "type_key": type_key,
                    "handles": [f"0x{handle:08X}" for handle in handles],
                }
                for type_key, handles in self.reused_type_keys
            ],
        }


def _normalise_samples(
    samples: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
) -> tuple[tuple[str, bytes], ...]:
    entries = tuple(samples.items()) if isinstance(samples, Mapping) else tuple(samples)
    if not entries:
        raise ValueError("at least one S2 save sample is required")
    labels: set[str] = set()
    normalised: list[tuple[str, bytes]] = []
    for label, data in entries:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("sample label must be a non-empty string")
        if label in labels:
            raise ValueError(f"duplicate sample label {label!r}")
        if not isinstance(data, bytes):
            raise TypeError(f"sample {label!r} must contain bytes")
        labels.add(label)
        normalised.append((label, data))
    return tuple(sorted(normalised, key=lambda item: item[0]))


def _item_observations(
    label: str,
    sha256: str,
    info: SaveInfo,
) -> tuple[S2ItemObservation, ...]:
    return tuple(
        S2ItemObservation(
            sample=label,
            sha256=sha256,
            handle=item.handle,
            type_key=item.type_key,
            category=item.category,
            count=item.count,
        )
        for item in info.inventory
    )


def analyze_s2_samples(
    samples: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
) -> S2MappingReport:
    """Compare parsed S2 inventory keys without assigning any human SID.

    ``samples`` is an in-memory mapping of safe caller-chosen labels to save
    bytes.  The function validates each save through the existing parser and
    reports only hashes, counts and compact observations.  It is suitable for
    controlled research pairs, but a confirmed mapping still requires a known
    SID acquisition and the project's game load/re-save gate.
    """

    entries = _normalise_samples(samples)
    summaries: list[S2SampleSummary] = []
    observations: list[S2ItemObservation] = []
    for label, data in entries:
        info = inspect_save(data, with_inventory=True)
        sha256 = hashlib.sha256(data).hexdigest()
        summaries.append(
            S2SampleSummary(
                sample=label,
                sha256=sha256,
                item_count=len(info.inventory),
                owned_count=len(info.owned_handles),
                grid_cell_count=info.grid_cell_count,
                unique_type_key_count=len({item.type_key for item in info.inventory}),
            )
        )
        observations.extend(_item_observations(label, sha256, info))

    by_handle: dict[int, list[S2ItemObservation]] = defaultdict(list)
    by_key: dict[str, set[int]] = defaultdict(set)
    for observation in observations:
        by_handle[observation.handle].append(observation)
        by_key[observation.type_key].add(observation.handle)

    shared_handles = tuple(
        S2HandleComparison(
            handle=handle,
            observations=tuple(sorted(rows, key=lambda item: item.sample)),
            stable_type_key=len({item.type_key for item in rows}) == 1,
        )
        for handle, rows in sorted(by_handle.items())
        if len({item.sample for item in rows}) >= 2
    )
    reused_type_keys = tuple(
        (type_key, tuple(sorted(handles)))
        for type_key, handles in sorted(by_key.items())
        if len(handles) >= 2
    )
    return S2MappingReport(
        samples=tuple(summaries),
        shared_handles=shared_handles,
        reused_type_keys=reused_type_keys,
    )


__all__ = [
    "S2HandleComparison",
    "S2ItemObservation",
    "S2MappingReport",
    "S2SampleSummary",
    "analyze_s2_samples",
]
