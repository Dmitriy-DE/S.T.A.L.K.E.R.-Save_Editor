"""Local Steam Auto-Cloud folders for games that sync saves on exit.

S.T.A.L.K.E.R. 2 keeps its saves under Steam Auto-Cloud root
``WinAppDataLocal``.  ``ISteamRemoteStorage::FileWrite`` writes to the default
root instead, so the game never sees such a file.  The working path is the one
the game itself uses: put the file into the local Auto-Cloud folder while a
Steam API session runs as the game, then end that session; Steam uploads
changed files when the "game" exits (docs/roadmap/SC-steam.md, SC-1).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from editor.releases import release_by_id

# Remote names of this game start with this folder under WinAppDataLocal.
_AUTO_CLOUD_TOP = {"stalker2": "Stalker2"}


def auto_cloud_release(app_id: int) -> str | None:
    """Return the release id whose saves use local Auto-Cloud, if any."""

    for release_id in _AUTO_CLOUD_TOP:
        if release_by_id(release_id).app_id == int(app_id):
            return release_id
    return None


def _proton_local_roots(app_id: int, libraries: Iterable[Path]) -> list[Path]:
    roots: list[Path] = []
    for library in libraries:
        user = Path(library) / "steamapps" / "compatdata" / str(app_id) / "pfx" / "drive_c" / "users" / "steamuser"
        # Steam itself creates the legacy spelling when the game is not
        # installed; a full Proton prefix links it to AppData/Local.
        roots.extend((user / "Local Settings" / "Application Data", user / "AppData" / "Local"))
    return roots


def auto_cloud_local_root(
    app_id: int,
    *,
    system: str | None = None,
    environ: Mapping[str, str] | None = None,
    libraries: Iterable[Path] | None = None,
) -> Path | None:
    """Return the existing local ``WinAppDataLocal`` folder for ``app_id``."""

    release_id = auto_cloud_release(app_id)
    if release_id is None:
        return None
    top = _AUTO_CLOUD_TOP[release_id]
    env = os.environ if environ is None else environ
    name = (system or sys.platform).casefold()
    if name.startswith("win"):
        local = env.get("LOCALAPPDATA")
        candidates = [Path(local)] if local else []
    else:
        if libraries is None:
            from editor.platforms import steam_libraries

            libraries = steam_libraries()
        candidates = _proton_local_roots(int(app_id), libraries)
    for root in candidates:
        if (root / top).is_dir():
            return root
    return None


def auto_cloud_local_path(root: Path, remote_name: str) -> Path:
    """Map a cloud name to its local file, refusing anything outside ``root``."""

    parts = str(remote_name).replace("\\", "/").split("/")
    if not remote_name or any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe Auto-Cloud name: {remote_name!r}")
    return Path(root).joinpath(*parts)


__all__ = ["auto_cloud_local_path", "auto_cloud_local_root", "auto_cloud_release"]
