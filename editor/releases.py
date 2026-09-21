"""Official S.T.A.L.K.E.R. release descriptors.

The descriptors are identification and path-search metadata only.  A release
does not become parser-supported until a matching format profile is registered
and its evidence row is accepted.
"""

from __future__ import annotations

from dataclasses import dataclass


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


__all__ = [
    "ReleaseDescriptor",
    "official_releases",
    "release_by_app_id",
    "release_by_id",
]
