"""Steam achievements through ``ISteamUserStats`` (SC-3).

Runs inside the native child process, initialised as the selected game, like
the cloud operations.  Listing is read-only; unlocking and clearing change the
player's Steam profile and are only started by an explicit user action.
"""

from __future__ import annotations

import ctypes
import time
from dataclasses import asdict, dataclass
from typing import Any

_USER_STATS_ACCESSORS = tuple(f"SteamAPI_SteamUserStats_v{v:03d}" for v in (13, 12, 11))


class AchievementError(RuntimeError):
    """Steam refused or could not provide achievement data."""


@dataclass(frozen=True)
class Achievement:
    api_name: str
    name: str
    description: str
    achieved: bool
    unlock_time: int
    hidden: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class _UserStats:
    def __init__(self, lib: ctypes.CDLL, run_callbacks: Any) -> None:
        c = ctypes
        accessor = next((getattr(lib, name) for name in _USER_STATS_ACCESSORS if hasattr(lib, name)), None)
        if accessor is None:
            raise AchievementError("libsteam_api не экспортирует ISteamUserStats")
        accessor.restype = c.c_void_p
        accessor.argtypes = []
        self._stats = accessor()
        if not self._stats:
            raise AchievementError("ISteamUserStats недоступен")
        self._run_callbacks = run_callbacks

        def bind(name: str, restype: Any, argtypes: list[Any]) -> Any:
            function = getattr(lib, f"SteamAPI_ISteamUserStats_{name}")
            function.restype = restype
            function.argtypes = [c.c_void_p, *argtypes]
            return function

        self._count = bind("GetNumAchievements", c.c_uint32, [])
        self._name = bind("GetAchievementName", c.c_char_p, [c.c_uint32])
        self._attribute = bind("GetAchievementDisplayAttribute", c.c_char_p, [c.c_char_p, c.c_char_p])
        self._get = bind(
            "GetAchievementAndUnlockTime",
            c.c_bool,
            [c.c_char_p, c.POINTER(c.c_bool), c.POINTER(c.c_uint32)],
        )
        self._set = bind("SetAchievement", c.c_bool, [c.c_char_p])
        self._clear = bind("ClearAchievement", c.c_bool, [c.c_char_p])
        self._store = bind("StoreStats", c.c_bool, [])

    def wait_ready(self, timeout: float = 10.0) -> int:
        # Current SDKs request the user's stats during init; they arrive
        # through callbacks.
        deadline = time.monotonic() + timeout
        while True:
            self._run_callbacks()
            count = int(self._count(self._stats))
            if count or time.monotonic() >= deadline:
                return count
            time.sleep(0.2)

    def _text(self, api_name: bytes, key: bytes) -> str:
        value = self._attribute(self._stats, api_name, key)
        return value.decode("utf-8", "replace") if value else ""

    def list(self) -> list[Achievement]:
        count = self.wait_ready()
        if not count:
            raise AchievementError("Steam не вернул достижения этой игры (у игры их нет или статистика не загрузилась)")
        result: list[Achievement] = []
        for index in range(count):
            raw = self._name(self._stats, index)
            if not raw:
                continue
            achieved = ctypes.c_bool(False)
            unlocked = ctypes.c_uint32(0)
            if not self._get(self._stats, raw, ctypes.byref(achieved), ctypes.byref(unlocked)):
                raise AchievementError(f"Steam не отдал состояние {raw.decode('utf-8', 'replace')}")
            result.append(
                Achievement(
                    api_name=raw.decode("utf-8", "replace"),
                    name=self._text(raw, b"name"),
                    description=self._text(raw, b"desc"),
                    achieved=bool(achieved.value),
                    unlock_time=int(unlocked.value),
                    hidden=self._text(raw, b"hidden") == "1",
                )
            )
        return result

    def set(self, api_name: str, achieved: bool) -> Achievement:
        known = {item.api_name: item for item in self.list()}
        if api_name not in known:
            raise AchievementError(f"у игры нет достижения {api_name}")
        raw = api_name.encode("utf-8")
        changed = self._set(self._stats, raw) if achieved else self._clear(self._stats, raw)
        if not changed or not self._store(self._stats):
            raise AchievementError(f"Steam отказал в изменении {api_name}")
        # Let StoreStats reach Steam before the child shuts the API down.
        for _ in range(10):
            self._run_callbacks()
            time.sleep(0.2)
        after = {item.api_name: item for item in self.list()}[api_name]
        if after.achieved != achieved:
            raise AchievementError(f"Steam не подтвердил изменение {api_name}")
        return after


def user_stats(worker: Any) -> _UserStats:
    """Bind ``ISteamUserStats`` on an initialised :class:`SteamNativeWorker`."""

    return _UserStats(worker._lib, worker._run_callbacks)


__all__ = ["Achievement", "AchievementError", "user_stats"]
