"""Small per-user interface preferences: language, sound and motion.

Kept apart from ``settings.json`` (save-location overrides) so a broken or
future preference never blocks path recovery.  Unknown or invalid values fall
back to defaults instead of raising.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .platforms import user_data_dir

PREFERENCES_FILE_NAME = "preferences.json"


@dataclass(frozen=True)
class Preferences:
    language: str | None = None  # None → follow the system locale
    sound: bool = True
    sound_volume: int = 25  # percent; UI cues are meant to stay quiet
    motion: bool = True

    def with_(self, **changes: object) -> Preferences:
        return replace(self, **changes)


def preferences_path() -> Path:
    override = os.environ.get("STALKER_EDITOR_PREFERENCES")
    return Path(override) if override else user_data_dir() / PREFERENCES_FILE_NAME


def load_preferences(path: Path | None = None) -> Preferences:
    target = path or preferences_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Preferences()
    if not isinstance(payload, dict):
        return Preferences()
    defaults = Preferences()
    language = payload.get("language")
    volume = payload.get("sound_volume", defaults.sound_volume)
    return Preferences(
        language=language if isinstance(language, str) and language else None,
        sound=payload.get("sound") if isinstance(payload.get("sound"), bool) else defaults.sound,
        sound_volume=max(0, min(100, volume)) if isinstance(volume, int) else defaults.sound_volume,
        motion=payload.get("motion") if isinstance(payload.get("motion"), bool) else defaults.motion,
    )


def save_preferences(preferences: Preferences, path: Path | None = None) -> None:
    target = path or preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(asdict(preferences), ensure_ascii=False, indent=2).encode("utf-8")
    fd, temp = tempfile.mkstemp(prefix=".preferences-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


__all__ = ["Preferences", "load_preferences", "preferences_path", "save_preferences"]
