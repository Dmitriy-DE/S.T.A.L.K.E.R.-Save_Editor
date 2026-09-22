"""Release-aware Steam Cloud file profiles.

Steam exposes Auto-Cloud files with paths relative to the game's configured
root.  The editor used to keep the S.T.A.L.K.E.R. 2 path in three separate
workers, which made every other official release look like an empty cloud.
This module is the single allow-list for save paths; sidecars and unrelated
screenshots stay out of the editor's save picker.
"""

from __future__ import annotations

from dataclasses import dataclass

from .releases import ReleaseDescriptor, official_releases, release_by_app_id, release_by_id


def is_editor_cloud_artifact(name: str) -> bool:
    """Return whether a cloud path is an editor-generated recovery artifact."""

    normalized = str(name or "").replace("\\", "/").rstrip("/")
    leaf = normalized.rsplit("/", 1)[-1]
    stem = leaf.rsplit(".", 1)[0] if "." in leaf else leaf
    return stem.casefold().endswith(("-edited", ".edited"))


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
        parts = normalized.split("/")
        if not normalized or any(part in {"", ".", ".."} for part in parts):
            return False
        if is_editor_cloud_artifact(normalized):
            return False
        for prefix in self.remote_prefixes:
            normalized_prefix = prefix.casefold().lstrip("/")
            if not folded.startswith(normalized_prefix):
                continue
            leaf = normalized[len(normalized_prefix) :]
            if not leaf or "/" in leaf:
                continue
            # Steam's original and Enhanced UFS entries use pattern ``*``
            # under the savedgames directory.  Keep the directory boundary
            # authoritative and let the format detector reject foreign bytes.
            if not self.extensions or any(
                leaf.casefold().endswith(extension.casefold())
                for extension in self.extensions
            ):
                return True
        return False

    @property
    def save_label(self) -> str:
        """Compact path description suitable for the cloud tab status line."""

        if len(self.remote_prefixes) == 1:
            prefix = self.remote_prefixes[0]
            suffix = " / ".join(sorted(self.extensions)) or "*"
            return f"{prefix}* ({suffix})"
        return f"{self.title} saves"


def _profile_for_release(release: ReleaseDescriptor) -> SteamCloudProfile:
    """Project one registry descriptor into the Cloud path contract."""

    return SteamCloudProfile(
        release.id,
        release.app_id,
        release.title,
        release.cloud_prefixes,
        release.cloud_extensions,
    )


_PROFILES = tuple(_profile_for_release(release) for release in official_releases())
_BY_RELEASE = {profile.release_id: profile for profile in _PROFILES}
_BY_APP_ID = {profile.app_id: profile for profile in _PROFILES}


def steam_cloud_profiles() -> tuple[SteamCloudProfile, ...]:
    """Return official profiles in the same order as the release selector."""

    return _PROFILES


def steam_cloud_profile_for_release(release_id: str) -> SteamCloudProfile:
    """Resolve a release or fail rather than guessing a cloud path."""

    try:
        release = release_by_id(release_id)
        return _BY_RELEASE[release.id]
    except KeyError as exc:
        raise KeyError(f"Unknown Steam Cloud release: {release_id!r}") from exc


def steam_cloud_profile_for_app_id(app_id: int) -> SteamCloudProfile:
    """Resolve a Steam app ID or fail closed for an unsupported game."""

    try:
        release = release_by_app_id(app_id)
        return _BY_APP_ID[release.app_id]
    except (KeyError, TypeError, ValueError) as exc:
        raise KeyError(f"Unsupported Steam Cloud app_id: {app_id!r}") from exc


__all__ = [
    "SteamCloudProfile",
    "is_editor_cloud_artifact",
    "steam_cloud_profile_for_app_id",
    "steam_cloud_profile_for_release",
    "steam_cloud_profiles",
]
