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


_OFFICIAL_RELEASES = (
    ReleaseDescriptor(
        id="stalker2",
        family="stalker2",
        edition="s2",
        title="S.T.A.L.K.E.R. 2: Heart of Chornobyl",
        app_ids=(1643320,),
        extensions=frozenset({".sav"}),
    ),
    ReleaseDescriptor(
        id="stalker-soc",
        family="soc",
        edition="original",
        title="S.T.A.L.K.E.R.: Shadow of Chernobyl",
        app_ids=(4500,),
        extensions=frozenset({".sav"}),
    ),
    ReleaseDescriptor(
        id="stalker-cs",
        family="clear_sky",
        edition="original",
        title="S.T.A.L.K.E.R.: Clear Sky",
        app_ids=(20510,),
        extensions=frozenset({".sav"}),
    ),
    ReleaseDescriptor(
        id="stalker-cop",
        family="cop",
        edition="original",
        title="S.T.A.L.K.E.R.: Call of Pripyat",
        app_ids=(41700,),
        extensions=frozenset({".scop", ".sav"}),
    ),
    ReleaseDescriptor(
        id="stalker-soc-ee",
        family="soc",
        edition="enhanced",
        title="S.T.A.L.K.E.R.: Shadow of Chornobyl — Enhanced Edition",
        app_ids=(2427410,),
        extensions=frozenset({".sav", ".dds", ".info"}),
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
    ),
    ReleaseDescriptor(
        id="stalker-cop-ee",
        family="cop",
        edition="enhanced",
        title="S.T.A.L.K.E.R.: Call of Pripyat — Enhanced Edition",
        app_ids=(2427430,),
        extensions=frozenset({".sav", ".scop", ".scs", ".dds", ".info"}),
    ),
)
_BY_ID = {release.id: release for release in _OFFICIAL_RELEASES}


def official_releases() -> tuple[ReleaseDescriptor, ...]:
    """Return official descriptors in stable UI order."""

    return _OFFICIAL_RELEASES


def release_by_id(release_id: str) -> ReleaseDescriptor:
    """Return one official descriptor or reject mods/unknown IDs."""

    try:
        return _BY_ID[release_id]
    except KeyError as exc:
        raise KeyError(f"Unknown official release: {release_id!r}") from exc


__all__ = ["ReleaseDescriptor", "official_releases", "release_by_id"]
