from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from editor.steam_profiles import is_editor_cloud_artifact

__all__ = [
    "APP_ID",
    "LIVE_WRITE_OVERRIDE_ENV",
    "SAVE_PREFIX",
    "CloudFile",
    "CloudFileFilter",
    "CloudSource",
    "SteamCloudError",
    "cloud_source_label",
    "default_cloud_file_filter",
]

LIVE_WRITE_OVERRIDE_ENV = "STALKER2_ALLOW_LIVE_CLOUD"


def _refuse_automated_live_session(app_id: int, action: str) -> None:
    """Block a real S.T.A.L.K.E.R. 2 cloud session started by a test run.

    Automated tests may not connect to or write the game's live cloud. Tests
    use fake native/CDP transports; the override is reserved for deliberate
    manual runs.
    """

    if app_id != APP_ID or "PYTEST_CURRENT_TEST" not in os.environ:
        return
    if os.environ.get(LIVE_WRITE_OVERRIDE_ENV) == "1":
        return
    raise SteamCloudError(
        f"Отказ: {action} для app_id={APP_ID} из автоматического теста. "
        "Используй fake transport; для осознанного ручного прогона установи "
        f"{LIVE_WRITE_OVERRIDE_ENV}=1."
    )


APP_ID = 1643320
SAVE_PREFIX = "Stalker2/Saved/STEAM/SaveGames/Data/"
MAX_FILE_BYTES = 64 * 1024 * 1024

CloudFileFilter = Callable[[str], bool]
CloudSource = Literal[
    "native_remote_storage",
    "web",
    "steam_cache_local",
    "steam_cache_metadata",
    "unknown",
]

_CLOUD_SOURCE_LABELS: dict[CloudSource, str] = {
    "native_remote_storage": "Steam RemoteStorage",
    "web": "Steam Cloud web",
    "steam_cache_local": "Steam cache · локальная копия",
    "steam_cache_metadata": "Steam cache · метаданные",
    "unknown": "Неизвестно",
}


def cloud_source_label(source: str) -> str:
    """Return a short user-facing label for cloud provenance."""

    return _CLOUD_SOURCE_LABELS.get(
        cast(CloudSource, source),
        _CLOUD_SOURCE_LABELS["unknown"],
    )


def default_cloud_file_filter(name: str) -> bool:
    """Keep backwards-compatible S.T.A.L.K.E.R. 2 filtering by default."""

    normalized = str(name or "").replace("\\", "/")
    return (
        not is_editor_cloud_artifact(normalized)
        and normalized.startswith(SAVE_PREFIX)
        and normalized.casefold().endswith(".sav")
    )


class SteamCloudError(RuntimeError):
    pass


@dataclass
class CloudFile:
    name: str
    size: int
    timestamp: int
    is_persisted: bool
    exists: bool
    # Steam's web cloud page exposes a short-lived download URL even when the
    # client RemoteStorage API returns no file list. Native callers do
    # not populate it, so the field stays optional and backwards-compatible.
    download_url: str | None = None
    local_path: Path | None = None
    # Keep this additive and last so existing positional adapters remain valid.
    source: CloudSource = "unknown"
