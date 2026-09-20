"""Release-aware Steam Cloud file profiles.

Steam exposes Auto-Cloud files with paths relative to the game's configured
root.  The editor used to keep the S.T.A.L.K.E.R. 2 path in three separate
workers, which made every other official release look like an empty cloud.
This module is the single allow-list for save paths; sidecars and unrelated
screenshots stay out of the editor's save picker.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SteamCloudProfile:
    """One official release's app identity and editable save path rules."""

    release_id: str
    app_id: int
    title: str
    remote_prefixes: tuple[str, ...]
    extensions: frozenset[str]

    def accepts(self, name: str) -> bool:
        """Return whether a RemoteStorage path is an editor save for this release."""

        normalized = str(name or "").replace("\\", "/").lstrip("/")
        folded = normalized.casefold()
        if not any(
            folded.startswith(prefix.casefold().lstrip("/"))
            for prefix in self.remote_prefixes
        ):
            return False
        # Steam's original and Enhanced UFS entries use pattern ``*`` under
        # the savedgames directory.  Keep the directory boundary as the
        # authoritative allow-list and let the format detector reject
        # thumbnails/foreign bytes later; do not hide extensionless saves.
        return not self.extensions or any(
            folded.endswith(extension.casefold()) for extension in self.extensions
        )

    @property
    def save_label(self) -> str:
        """Compact path description suitable for the cloud tab status line."""

        if len(self.remote_prefixes) == 1:
            prefix = self.remote_prefixes[0]
            suffix = " / ".join(sorted(self.extensions)) or "*"
            return f"{prefix}* ({suffix})"
        return f"{self.title} saves"


_PROFILES = (
    SteamCloudProfile(
        "stalker2",
        1643320,
        "S.T.A.L.K.E.R. 2: Heart of Chornobyl",
        ("Stalker2/Saved/STEAM/SaveGames/Data/",),
        frozenset({".sav"}),
    ),
    SteamCloudProfile(
        "stalker-soc",
        4500,
        "S.T.A.L.K.E.R.: Shadow of Chernobyl",
        ("_appdata_/savedgames/",),
        frozenset(),
    ),
    SteamCloudProfile(
        "stalker-cs",
        20510,
        "S.T.A.L.K.E.R.: Clear Sky",
        ("_appdata_/savedgames/",),
        frozenset(),
    ),
    SteamCloudProfile(
        "stalker-cop",
        41700,
        "S.T.A.L.K.E.R.: Call of Pripyat",
        ("_appdata_/savedgames/",),
        frozenset(),
    ),
    SteamCloudProfile(
        "stalker-soc-ee",
        2427410,
        "S.T.A.L.K.E.R.: Shadow of Chornobyl — Enhanced Edition",
        ("STALKER Shadow of Chornobyl - EE/STEAM/savedgames/",),
        frozenset(),
    ),
    SteamCloudProfile(
        "stalker-cs-ee",
        2427420,
        "S.T.A.L.K.E.R.: Clear Sky — Enhanced Edition",
        ("STALKER Clear Sky - EE/STEAM/savedgames/",),
        frozenset(),
    ),
    SteamCloudProfile(
        "stalker-cop-ee",
        2427430,
        "S.T.A.L.K.E.R.: Call of Pripyat — Enhanced Edition",
        ("STALKER Call of Prypiat - EE/STEAM/savedgames/",),
        frozenset(),
    ),
)
_BY_RELEASE = {profile.release_id: profile for profile in _PROFILES}
_BY_APP_ID = {profile.app_id: profile for profile in _PROFILES}


def steam_cloud_profiles() -> tuple[SteamCloudProfile, ...]:
    """Return official profiles in the same order as the release selector."""

    return _PROFILES


def steam_cloud_profile_for_release(release_id: str) -> SteamCloudProfile:
    """Resolve a release or fail rather than guessing a cloud path."""

    try:
        return _BY_RELEASE[release_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Steam Cloud release: {release_id!r}") from exc


def steam_cloud_profile_for_app_id(app_id: int) -> SteamCloudProfile:
    """Resolve a Steam app ID or fail closed for an unsupported game."""

    try:
        return _BY_APP_ID[int(app_id)]
    except (KeyError, TypeError, ValueError) as exc:
        raise KeyError(f"Unsupported Steam Cloud app_id: {app_id!r}") from exc


__all__ = [
    "SteamCloudProfile",
    "steam_cloud_profile_for_app_id",
    "steam_cloud_profile_for_release",
    "steam_cloud_profiles",
]
