"""Official S.T.A.L.K.E.R. release descriptors and equipment registry.

The descriptors own release/edition identity, paths and the canonical
equipment vocabulary consumed by parser, catalog and UI projections. A
release does not become parser-supported until a matching format profile is
registered and its evidence row is accepted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, cast

from .capability_types import CapabilitySupport

EquipmentFeature = Literal["durability", "upgrades", "placement", "add", "remove"]
_EQUIPMENT_FEATURES: tuple[EquipmentFeature, ...] = (
    "durability",
    "upgrades",
    "placement",
    "add",
    "remove",
)


@dataclass(frozen=True)
class EquipmentRegistry:
    """Canonical equipment vocabulary and maturity for one release.

    Keeping this beside the release descriptor prevents parser, catalog, UI
    and Cloud code from silently growing separate game/edition registries.
    Format-specific binary writers still live in their own modules.
    """

    categories: tuple[str, ...]
    device_subtypes: tuple[str, ...]
    icon_source: str
    feature_support: Mapping[EquipmentFeature, CapabilitySupport]

    def __post_init__(self) -> None:
        categories = tuple(dict.fromkeys(str(value) for value in self.categories))
        subtypes = tuple(dict.fromkeys(str(value) for value in self.device_subtypes))
        support = dict(self.feature_support)
        unknown = set(support) - set(_EQUIPMENT_FEATURES)
        missing = set(_EQUIPMENT_FEATURES) - set(support)
        if unknown:
            raise ValueError(f"unknown equipment feature: {sorted(unknown)!r}")
        if missing:
            raise ValueError(f"missing equipment feature: {sorted(missing)!r}")
        if not categories or "other" not in categories:
            raise ValueError("equipment registry must include an other fallback")
        if not self.icon_source.strip():
            raise ValueError("equipment registry requires icon_source")
        normalized = cast(
            Mapping[EquipmentFeature, CapabilitySupport],
            {feature: support[feature] for feature in _EQUIPMENT_FEATURES},
        )
        object.__setattr__(self, "categories", categories)
        object.__setattr__(self, "device_subtypes", subtypes)
        object.__setattr__(self, "feature_support", MappingProxyType(normalized))

    def support(self, feature: EquipmentFeature) -> CapabilitySupport:
        if feature not in _EQUIPMENT_FEATURES:
            raise KeyError(f"unknown equipment feature: {feature!r}")
        return self.feature_support[feature]


def _support(**values: CapabilitySupport) -> Mapping[EquipmentFeature, CapabilitySupport]:
    return cast(Mapping[EquipmentFeature, CapabilitySupport], values)


_XRAY_CATEGORIES = (
    "weapon",
    "armor",
    "module",
    "device",
    "consumable",
    "ammo",
    "artifact",
    "quest",
    "other",
)
_S2_CATEGORIES = (
    "weapon",
    "armor",
    "helmet",
    "module",
    "device",
    "consumable",
    "ammo",
    "artifact",
    "quest",
    "other",
)
_XRAY_DEVICE_SUBTYPES = ("detector", "other", "unknown")
_S2_DEVICE_SUBTYPES = ("nvg", "binocular", "detector", "other", "unknown")

_S2_EQUIPMENT = EquipmentRegistry(
    categories=_S2_CATEGORIES,
    device_subtypes=_S2_DEVICE_SUBTYPES,
    icon_source=(
        "official loose CFG/localization; selected Zone Kit/Workshop "
        "is presentation-only"
    ),
    feature_support=_support(
        durability=CapabilitySupport(
            "experimental",
            "S2 weapon/armor condition anchor is source-backed; game load/re-save is not accepted yet.",
        ),
        upgrades=CapabilitySupport(
            "research",
            "S2 module/upgrade vectors are observed but installed/current state is not proven.",
        ),
        placement=CapabilitySupport(
            "unsupported", "S2 placement serialization is not confirmed."
        ),
        add=CapabilitySupport("unsupported", "S2 add/clone constructor is not confirmed."),
        remove=CapabilitySupport("unsupported", "S2 safe remove/reference graph is not confirmed."),
    ),
)


def _xray_equipment(
    *,
    upgrades: CapabilitySupport,
    categories: tuple[str, ...] = _XRAY_CATEGORIES,
) -> EquipmentRegistry:
    return EquipmentRegistry(
        categories=categories,
        device_subtypes=_XRAY_DEVICE_SUBTYPES,
        icon_source="official X-Ray game resources",
        feature_support=_support(
            durability=CapabilitySupport(
                "experimental",
                "X-Ray condition writer requires game load/re-save evidence.",
            ),
            upgrades=upgrades,
            placement=CapabilitySupport(
                "experimental",
                "X-Ray placement anchor requires game load/re-save evidence.",
            ),
            add=CapabilitySupport(
                "experimental",
                "X-Ray structural add writer requires game load/re-save evidence.",
            ),
            remove=CapabilitySupport(
                "experimental",
                "X-Ray structural remove writer requires game load/re-save evidence.",
            ),
        ),
    )


_COP_EQUIPMENT = _xray_equipment(
    categories=(*_XRAY_CATEGORIES[:-1], "helmet", "other"),
    upgrades=CapabilitySupport(
        "experimental", "m_upgrades vector requires game load/re-save evidence."
    ),
)
_EE_EQUIPMENT = EquipmentRegistry(
    categories=_XRAY_CATEGORIES,
    device_subtypes=_XRAY_DEVICE_SUBTYPES,
    icon_source="unavailable until an Enhanced Edition resource sample is accepted",
    feature_support=_support(
        durability=CapabilitySupport(
            "unsupported", "Enhanced Edition parser/equipment sample is not accepted."
        ),
        upgrades=CapabilitySupport(
            "unsupported", "Enhanced Edition parser/equipment sample is not accepted."
        ),
        placement=CapabilitySupport(
            "unsupported", "Enhanced Edition parser/equipment sample is not accepted."
        ),
        add=CapabilitySupport(
            "unsupported", "Enhanced Edition parser/equipment sample is not accepted."
        ),
        remove=CapabilitySupport(
            "unsupported", "Enhanced Edition parser/equipment sample is not accepted."
        ),
    ),
)


@dataclass(frozen=True)
class ReleaseDescriptor:
    """One official game/release family visible to the UI."""

    id: str
    family: str
    edition: str
    title: str
    app_ids: tuple[int, ...]
    extensions: frozenset[str]
    install_dirs: tuple[str, ...] = ()
    cloud_prefixes: tuple[str, ...] = ()
    cloud_extensions: frozenset[str] = frozenset()
    equipment: EquipmentRegistry | None = None

    @property
    def is_xray_original(self) -> bool:
        """Whether this registry entry is one of the supported original X-Ray releases."""

        return self.edition == "original" and self.family != "stalker2"

    @property
    def app_id(self) -> int:
        """Return the sole Steam app ID owned by this release descriptor."""

        if len(self.app_ids) != 1:
            raise ValueError(
                f"release {self.id!r} must own exactly one Steam app ID"
            )
        return self.app_ids[0]


_OFFICIAL_RELEASES = (
    ReleaseDescriptor(
        id="stalker2",
        family="stalker2",
        edition="s2",
        title="S.T.A.L.K.E.R. 2: Heart of Chornobyl",
        app_ids=(1643320,),
        extensions=frozenset({".sav"}),
        install_dirs=(
            "S.T.A.L.K.E.R. 2 Heart of Chornobyl",
            "STALKER 2 Heart of Chornobyl",
            "S.T.A.L.K.E.R. 2",
        ),
        cloud_prefixes=("Stalker2/Saved/STEAM/SaveGames/Data/",),
        cloud_extensions=frozenset({".sav"}),
        equipment=_S2_EQUIPMENT,
    ),
    ReleaseDescriptor(
        id="stalker-soc",
        family="soc",
        edition="original",
        title="S.T.A.L.K.E.R.: Shadow of Chernobyl",
        app_ids=(4500,),
        extensions=frozenset({".sav"}),
        install_dirs=("STALKER Shadow of Chernobyl", "STALKER Shadow of Chornobyl"),
        cloud_prefixes=("_appdata_/savedgames/",),
        equipment=_xray_equipment(
            upgrades=CapabilitySupport("unsupported", "SoC upgrade writer is not confirmed.")
        ),
    ),
    ReleaseDescriptor(
        id="stalker-cs",
        family="clear_sky",
        edition="original",
        title="S.T.A.L.K.E.R.: Clear Sky",
        app_ids=(20510,),
        extensions=frozenset({".sav"}),
        install_dirs=("STALKER Clear Sky",),
        cloud_prefixes=("_appdata_/savedgames/",),
        equipment=_xray_equipment(
            upgrades=CapabilitySupport(
                "experimental", "m_upgrades vector requires game load/re-save evidence."
            )
        ),
    ),
    ReleaseDescriptor(
        id="stalker-cop",
        family="cop",
        edition="original",
        title="S.T.A.L.K.E.R.: Call of Pripyat",
        app_ids=(41700,),
        extensions=frozenset({".scop", ".sav"}),
        install_dirs=("Stalker Call of Pripyat", "STALKER Call of Pripyat"),
        cloud_prefixes=("_appdata_/savedgames/",),
        equipment=_COP_EQUIPMENT,
    ),
    ReleaseDescriptor(
        id="stalker-soc-ee",
        family="soc",
        edition="enhanced",
        title="S.T.A.L.K.E.R.: Shadow of Chornobyl — Enhanced Edition",
        app_ids=(2427410,),
        extensions=frozenset({".sav", ".dds", ".info"}),
        install_dirs=("STALKER Shadow of Chornobyl - Enhanced Edition",),
        cloud_prefixes=("STALKER Shadow of Chornobyl - EE/STEAM/savedgames/",),
        equipment=_EE_EQUIPMENT,
    ),
    ReleaseDescriptor(
        id="stalker-cs-ee",
        family="clear_sky",
        edition="enhanced",
        title="S.T.A.L.K.E.R.: Clear Sky — Enhanced Edition",
        app_ids=(2427420,),
        # Community and cloud metadata report both X-Ray save spellings plus
        # the shared thumbnail/name sidecars.  These are candidate hints only;
        # no EE parser is enabled by this declaration.
        extensions=frozenset({".sav", ".scop", ".scs", ".dds", ".info"}),
        install_dirs=("STALKER Clear Sky - Enhanced Edition",),
        cloud_prefixes=("STALKER Clear Sky - EE/STEAM/savedgames/",),
        equipment=_EE_EQUIPMENT,
    ),
    ReleaseDescriptor(
        id="stalker-cop-ee",
        family="cop",
        edition="enhanced",
        title="S.T.A.L.K.E.R.: Call of Pripyat — Enhanced Edition",
        app_ids=(2427430,),
        extensions=frozenset({".sav", ".scop", ".scs", ".dds", ".info"}),
        install_dirs=("STALKER Call of Prypiat - Enhanced Edition",),
        cloud_prefixes=("STALKER Call of Prypiat - EE/STEAM/savedgames/",),
        equipment=_EE_EQUIPMENT,
    ),
)
_BY_ID = {release.id: release for release in _OFFICIAL_RELEASES}
_BY_APP_ID = {
    app_id: release
    for release in _OFFICIAL_RELEASES
    for app_id in release.app_ids
}


def _validate_registry() -> None:
    """Reject duplicate ownership or incomplete cross-surface metadata."""

    if len(_BY_ID) != len(_OFFICIAL_RELEASES):
        raise ValueError("official release IDs must be unique")
    if len(_BY_APP_ID) != sum(len(release.app_ids) for release in _OFFICIAL_RELEASES):
        raise ValueError("official Steam app IDs must be unique")
    for release in _OFFICIAL_RELEASES:
        if len(release.app_ids) != 1 or release.app_ids[0] <= 0:
            raise ValueError(f"release {release.id!r} must own one positive app ID")
        if not release.install_dirs or not release.cloud_prefixes:
            raise ValueError(f"release {release.id!r} lacks platform metadata")
        if release.equipment is None:
            raise ValueError(f"release {release.id!r} lacks equipment metadata")


_validate_registry()


def official_releases() -> tuple[ReleaseDescriptor, ...]:
    """Return official descriptors in stable UI order."""

    return _OFFICIAL_RELEASES


def release_by_id(release_id: str) -> ReleaseDescriptor:
    """Return one official descriptor or reject mods/unknown IDs."""

    try:
        return _BY_ID[release_id]
    except KeyError as exc:
        raise KeyError(f"Unknown official release: {release_id!r}") from exc


def release_by_app_id(app_id: int) -> ReleaseDescriptor:
    """Return the release owning a Steam app ID, or fail closed."""

    try:
        return _BY_APP_ID[int(app_id)]
    except (KeyError, TypeError, ValueError) as exc:
        raise KeyError(f"Unknown official Steam app ID: {app_id!r}") from exc


def is_xray_original_release(release_id: str | None) -> bool:
    """Return the canonical X-Ray routing predicate for an official release ID."""

    if not release_id:
        return False
    try:
        return release_by_id(str(release_id)).is_xray_original
    except KeyError:
        return False


__all__ = [
    "EquipmentFeature",
    "EquipmentRegistry",
    "ReleaseDescriptor",
    "is_xray_original_release",
    "official_releases",
    "release_by_app_id",
    "release_by_id",
]
