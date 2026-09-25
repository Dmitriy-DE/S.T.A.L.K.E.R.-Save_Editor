"""Quiet interface sounds and short transitions, both switchable at runtime.

Sounds are synthesised on first use (no game audio is redistributed), each
game with its own menu character: a heavy metal switch for Shadow of
Chernobyl, crackling static for Clear Sky, soft PDA clicks for Call of
Pripyat and airy blips for S.T.A.L.K.E.R. 2.  Qt Multimedia is imported lazily; any failure
leaves the editor silent instead of breaking it.
"""

from __future__ import annotations

import math
import os
import random
import struct
import wave
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QAbstractButton, QApplication, QGraphicsOpacityEffect, QWidget

from editor.platforms import user_data_dir
from editor.preferences import Preferences, load_preferences, save_preferences

SAMPLE_RATE = 22_050
SOUND_EVENTS = ("click", "tab", "open", "save", "error", "hover")
# Bump when the synthesis changes so cached WAVs from older builds are redone.
SOUND_VERSION = 2
# Relative loudness per event; "hover" is barely there, like the menus.
_EVENT_GAIN = {"hover": 0.35, "click": 0.8, "tab": 0.8, "open": 0.8, "save": 0.8, "error": 0.8}


def _envelope(index: int, total: int, attack: float = 0.004) -> float:
    t = index / SAMPLE_RATE
    attack_env = min(1.0, t / attack) if attack else 1.0
    return attack_env * math.exp(-5.0 * index / max(1, total))


def _tone(freqs: list[tuple[float, float]], *, square: bool, noise: float = 0.0) -> list[float]:
    """``freqs``: (frequency, seconds) segments, rendered back to back."""

    rng = random.Random(7)
    out: list[float] = []
    for freq, seconds in freqs:
        total = int(SAMPLE_RATE * seconds)
        phase = 0.0
        for index in range(total):
            phase += freq / SAMPLE_RATE
            value = math.sin(2 * math.pi * phase)
            if square:
                value = math.tanh(value * 4.0) * 0.6
            if noise:
                value += (rng.random() * 2 - 1) * noise
            out.append(value * _envelope(index, total))
    return out


def _pluck(freq: float, seconds: float, *, decay: float = 9.0, glide: float = 1.0) -> list[float]:
    """A damped sine; ``glide`` < 1 bends the pitch down like a relay."""

    total = int(SAMPLE_RATE * seconds)
    out: list[float] = []
    phase = 0.0
    for index in range(total):
        progress = index / max(1, total)
        phase += freq * (1.0 + (glide - 1.0) * progress) / SAMPLE_RATE
        out.append(math.sin(2 * math.pi * phase) * math.exp(-decay * progress) * min(1.0, index / 60))
    return out


def _noise(seconds: float, *, smooth: float, seed: int, crackle: float = 0.0) -> list[float]:
    """Low-passed noise burst (``smooth`` 0…1); ``crackle`` adds sparse pops."""

    rng = random.Random(seed)
    total = int(SAMPLE_RATE * seconds)
    out: list[float] = []
    value = 0.0
    for index in range(total):
        value = value * smooth + (rng.random() * 2 - 1) * (1.0 - smooth)
        pop = (rng.random() * 2 - 1) * 3.0 if crackle and rng.random() < crackle else 0.0
        out.append((value + pop * (1.0 - smooth)) * math.exp(-7.0 * index / max(1, total)))
    return out


def _mix(*layers: tuple[float, list[float]], gap: float = 0.0) -> list[float]:
    """Sum (offset seconds, samples) layers into one buffer."""

    length = max(int(offset * SAMPLE_RATE) + len(samples) for offset, samples in layers)
    out = [0.0] * (length + int(gap * SAMPLE_RATE))
    for offset, samples in layers:
        start = int(offset * SAMPLE_RATE)
        for index, value in enumerate(samples):
            out[start + index] += value
    return out


def _render_soc(event: str) -> list[float]:
    # Shadow of Chernobyl: a heavy metal switch — low thud under a dry clack.
    thud = _pluck(95, 0.12, decay=7, glide=0.8)
    clack = [v * 0.7 for v in _noise(0.03, smooth=0.35, seed=1)]
    return {
        "hover": _mix((0, [v * 0.5 for v in _noise(0.02, smooth=0.5, seed=2)])),
        "click": _mix((0, thud), (0, clack)),
        "tab": _mix((0, clack), (0.05, thud)),
        "open": _mix((0, thud), (0, clack), (0.09, _pluck(140, 0.16, decay=6, glide=0.7))),
        "save": _mix((0, clack), (0.06, _pluck(180, 0.1)), (0.14, _pluck(240, 0.14))),
        "error": _mix((0, _pluck(70, 0.25, decay=5, glide=0.6)), (0, clack)),
    }[event]


def _render_clear_sky(event: str) -> list[float]:
    # Clear Sky: the same hardware, but noisier — a crackle of static.
    static = [v * 0.8 for v in _noise(0.05, smooth=0.2, seed=3, crackle=0.02)]
    ping = _pluck(880, 0.06, decay=12)
    return {
        "hover": _mix((0, [v * 0.4 for v in _noise(0.025, smooth=0.25, seed=4, crackle=0.03)])),
        "click": _mix((0, static), (0.01, ping)),
        "tab": _mix((0, static), (0.04, _pluck(660, 0.06, decay=12))),
        "open": _mix((0, static), (0.05, _pluck(520, 0.08)), (0.12, _pluck(780, 0.1))),
        "save": _mix((0, static), (0.05, _pluck(780, 0.08)), (0.13, _pluck(1040, 0.12))),
        "error": _mix((0, _noise(0.2, smooth=0.1, seed=5, crackle=0.05)), (0, _pluck(110, 0.22, glide=0.7))),
    }[event]


def _render_cop(event: str) -> list[float]:
    # Call of Pripyat: softer, rounder clicks of a newer PDA.
    tick = [v * 0.4 for v in _noise(0.015, smooth=0.6, seed=6)]
    return {
        "hover": _mix((0, [v * 0.6 for v in _pluck(1200, 0.02, decay=14)])),
        "click": _mix((0, tick), (0, _pluck(720, 0.07, decay=10))),
        "tab": _mix((0, _pluck(600, 0.06, decay=10)), (0.045, _pluck(900, 0.07, decay=10))),
        "open": _mix((0, _pluck(480, 0.08)), (0.07, _pluck(640, 0.08)), (0.14, _pluck(960, 0.12))),
        "save": _mix((0, _pluck(820, 0.08)), (0.08, _pluck(1230, 0.14))),
        "error": _mix((0, _pluck(300, 0.22, decay=6, glide=0.7))),
    }[event]


def _render_stalker2(event: str) -> list[float]:
    # S.T.A.L.K.E.R. 2: modern, airy UI blips with a gentle pitch glide.
    base = 520.0
    return {
        "hover": _mix((0, [v * 0.6 for v in _pluck(base * 2, 0.03, decay=10, glide=1.05)])),
        "click": _mix((0, _pluck(base * 1.5, 0.05, decay=8, glide=1.04))),
        "tab": _mix((0, _pluck(base, 0.06)), (0.05, _pluck(base * 1.26, 0.07))),
        "open": _mix((0, _pluck(base * 0.75, 0.08)), (0.07, _pluck(base, 0.08)), (0.14, _pluck(base * 1.5, 0.12))),
        "save": _mix((0, _pluck(base * 1.5, 0.09)), (0.08, _pluck(base * 2, 0.16))),
        "error": _mix((0, _pluck(base * 0.5, 0.14, glide=0.9)), (0.11, _pluck(base * 0.42, 0.18, glide=0.9))),
    }[event]


_RENDERERS = {
    "soc": _render_soc,
    "clear_sky": _render_clear_sky,
    "cop": _render_cop,
    "stalker2": _render_stalker2,
}


def _render(event: str, theme: str) -> list[float]:
    samples = _RENDERERS.get(theme, _render_soc)(event)
    peak = max((abs(value) for value in samples), default=1.0) or 1.0
    gain = _EVENT_GAIN.get(event, 0.8)
    return [value / peak * gain for value in samples]


def write_wav(path: Path, samples: list[float]) -> None:
    # ``_render`` already normalises and applies the per-event gain.
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32767))
        for value in samples
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with wave.open(str(temp), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames)
    os.replace(temp, path)


def sound_theme(release_or_family: str | None) -> str:
    value = str(release_or_family or "").casefold()
    if value.startswith("stalker2") or value == "s2":
        return "stalker2"
    if "cop" in value or "pripyat" in value:
        return "cop"
    if "clear" in value or value.endswith("-cs") or value == "cs":
        return "clear_sky"
    return "soc"


class Effects(QObject):
    """Process-wide sound and motion switches backed by ``preferences.json``."""

    _instance: Effects | None = None

    def __init__(self, preferences: Preferences | None = None) -> None:
        super().__init__()
        self.preferences = preferences or load_preferences()
        self.theme = "soc"
        self._players: dict[tuple[str, str], Any] = {}
        self._audio_failed = bool(os.environ.get("PYTEST_CURRENT_TEST")) or (
            os.environ.get("QT_QPA_PLATFORM") == "offscreen"
        )
        self._cache = user_data_dir() / "sounds"

    @classmethod
    def instance(cls) -> Effects:
        if cls._instance is None:
            cls._instance = Effects()
        return cls._instance

    # --- switches -----------------------------------------------------
    @property
    def sound_enabled(self) -> bool:
        return self.preferences.sound

    @property
    def motion_enabled(self) -> bool:
        return self.preferences.motion

    def _store(self, preferences: Preferences) -> None:
        self.preferences = preferences
        try:
            save_preferences(preferences)
        except OSError:
            pass  # the switch still applies for this session

    def set_sound_enabled(self, enabled: bool) -> None:
        self._store(self.preferences.with_(sound=bool(enabled)))

    def set_motion_enabled(self, enabled: bool) -> None:
        self._store(self.preferences.with_(motion=bool(enabled)))

    def set_volume(self, percent: int) -> None:
        self._store(self.preferences.with_(sound_volume=max(0, min(100, int(percent)))))
        for player in self._players.values():
            player.setVolume(self._volume())

    def set_theme(self, release_or_family: str | None) -> None:
        self.theme = sound_theme(release_or_family)

    # --- sound --------------------------------------------------------
    def _volume(self) -> float:
        # Half-scale on top of the preference: cues must stay in the background.
        return self.preferences.sound_volume / 100 * 0.5

    def _player(self, event: str):
        key = (self.theme, event)
        if key in self._players:
            return self._players[key]
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
        except Exception:
            self._audio_failed = True
            return None
        path = self._cache / f"v{SOUND_VERSION}-{self.theme}-{event}.wav"
        if not path.is_file():
            try:
                write_wav(path, _render(event, self.theme))
            except OSError:
                self._audio_failed = True
                return None
        player = QSoundEffect(self)
        player.setSource(QUrl.fromLocalFile(str(path)))
        player.setVolume(self._volume())
        self._players[key] = player
        return player

    def play(self, event: str) -> None:
        if not self.sound_enabled or self._audio_failed or event not in SOUND_EVENTS:
            return
        try:
            player = self._player(event)
            if player is not None:
                player.play()
        except Exception:
            self._audio_failed = True

    # --- motion -------------------------------------------------------
    def fade_in(self, widget: QWidget | None, duration: int = 160) -> None:
        if not self.motion_enabled or widget is None:
            return
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(duration)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _done() -> None:
            # Graphics effects slow painting and clip native children; drop it.
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)  # type: ignore[arg-type]

        animation.finished.connect(_done)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


_HOVER_BUTTONS = frozenset({"globalNav", "categoryTab", "libraryGameButton", "settingsCategoryButton"})


class ClickSounds(QObject):
    """Application-wide event filter: a quiet blip for every button press."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            isinstance(event, QMouseEvent)
            and event.type() == QEvent.Type.MouseButtonRelease
            and isinstance(watched, QAbstractButton)
            and watched.isEnabled()
            and event.button() == Qt.MouseButton.LeftButton
            and watched.rect().contains(event.position().toPoint())
        ):
            kind = "tab" if watched.objectName() in {"globalNav", "categoryTab"} else "click"
            Effects.instance().play(kind)
        elif (
            event.type() == QEvent.Type.Enter
            and isinstance(watched, QAbstractButton)
            and watched.isEnabled()
            and watched.objectName() in _HOVER_BUTTONS
        ):
            # Game menus answer hovering over their items with a soft tick.
            Effects.instance().play("hover")
        return False


def install_click_sounds(app: QApplication) -> ClickSounds:
    handler = ClickSounds(app)
    app.installEventFilter(handler)
    return handler


__all__ = [
    "SOUND_EVENTS",
    "ClickSounds",
    "Effects",
    "install_click_sounds",
    "sound_theme",
    "write_wav",
]
