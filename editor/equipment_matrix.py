"""Release-scoped equipment projection backed by :mod:`editor.releases`.

The release registry owns the game/edition vocabulary and maturity reasons.
This module keeps the historical ``EquipmentProfile`` API used by the UI and
tests, while projecting the canonical metadata instead of maintaining a
second list of releases.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .capability_types import CapabilitySupport
from .releases import (
    EquipmentFeature,
    EquipmentRegistry,
    official_releases,
    release_by_id,
)

_FEATURES: tuple[EquipmentFeature, ...] = (
    "durability",
    "upgrades",
    "placement",
    "add",
    "remove",
)


@dataclass(frozen=True)
class EquipmentProfile:
    """Release-specific equipment vocabulary and independent feature gates."""

    release_id: str
    categories: tuple[str, ...]
    device_subtypes: tuple[str, ...]
    icon_source: str
    feature_support: Mapping[EquipmentFeature, CapabilitySupport]

    @classmethod
    def from_registry(
        cls,
        release_id: str,
        registry: EquipmentRegistry,
    ) -> EquipmentProfile:
        return cls(
            release_id=release_id,
            categories=registry.categories,
            device_subtypes=registry.device_subtypes,
            icon_source=registry.icon_source,
            feature_support=registry.feature_support,
        )

    def __post_init__(self) -> None:
        categories = tuple(dict.fromkeys(str(value) for value in self.categories))
        subtypes = tuple(dict.fromkeys(str(value) for value in self.device_subtypes))
        support = dict(self.feature_support)
        unknown = set(support) - set(_FEATURES)
        if unknown:
            raise ValueError(f"unknown equipment feature: {sorted(unknown)!r}")
        missing = set(_FEATURES) - set(support)
        if missing:
            raise ValueError(f"missing equipment feature: {sorted(missing)!r}")
        if not self.release_id.strip() or not self.icon_source.strip():
            raise ValueError("equipment profile requires release_id and icon_source")
        if not categories or "other" not in categories:
            raise ValueError("equipment profile must include an other fallback")
        object.__setattr__(self, "categories", categories)
        object.__setattr__(self, "device_subtypes", subtypes)
        object.__setattr__(self, "feature_support", MappingProxyType(support))

    def support(self, feature: EquipmentFeature) -> CapabilitySupport:
        """Return one independently gated feature."""

        if feature not in _FEATURES:
            raise KeyError(f"unknown equipment feature: {feature!r}")
        return self.feature_support[feature]

    def as_dict(self) -> dict[str, object]:
        return {
            "release_id": self.release_id,
            "categories": list(self.categories),
            "device_subtypes": list(self.device_subtypes),
            "icon_source": self.icon_source,
            "features": {
                name: self.support(name).as_dict() for name in _FEATURES
            },
        }


def _profile_for_release(release_id: str) -> EquipmentProfile:
    release = release_by_id(release_id)
    if release.equipment is None:  # defensive for externally constructed descriptors
        raise KeyError(f"Release {release_id!r} has no equipment registry")
    return EquipmentProfile.from_registry(release.id, release.equipment)


_PROFILES: tuple[EquipmentProfile, ...] = tuple(
    _profile_for_release(release.id) for release in official_releases()
)
_BY_ID = {profile.release_id: profile for profile in _PROFILES}


def equipment_profiles() -> tuple[EquipmentProfile, ...]:
    """Return the immutable matrix in official release order."""

    return _PROFILES


def equipment_profile_for_release(release_id: str) -> EquipmentProfile:
    """Resolve one release or fail closed instead of using a default profile."""

    try:
        return _BY_ID[release_id]
    except KeyError as exc:
        raise KeyError(f"Unknown equipment profile: {release_id!r}") from exc


__all__ = [
    "EquipmentFeature",
    "EquipmentProfile",
    "equipment_profile_for_release",
    "equipment_profiles",
]
