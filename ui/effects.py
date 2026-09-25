"""Quiet interface sounds and short transitions, both switchable at runtime.

Sounds are synthesised on first use (no game audio is redistributed): a
PDA-style square blip for the X-Ray trilogy, pitched per game, and a softer
sine for S.T.A.L.K.E.R. 2.  Qt Multimedia is imported lazily; any failure
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
SOUND_EVENTS = ("click", "tab", "open", "save", "error")
# X-Ray games share the PDA voice; the pitch tells them apart.
_THEME_PITCH = {"soc": 1.0, "clear_sky": 0.92, "cop": 1.08}


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
                # Soft-clipped square: the PDA beep without harsh aliasing.
                value = math.tanh(value * 4.0) * 0.6
            if noise:
                value += (rng.random() * 2 - 1) * noise
            out.append(value * _envelope(index, total))
    return out


def _render(event: str, theme: str) -> list[float]:
    if theme == "stalker2":
        base = 520.0
        table = {
            "click": [(base * 1.5, 0.035)],
            "tab": [(base, 0.05), (base * 1.26, 0.06)],
            "open": [(base * 0.75, 0.07), (base, 0.07), (base * 1.5, 0.1)],
            "save": [(base * 1.5, 0.08), (base * 2, 0.14)],
            "error": [(base * 0.5, 0.12), (base * 0.42, 0.16)],
        }
        return _tone(table[event], square=False, noise=0.01)
    pitch = _THEME_PITCH.get(theme, 1.0)
    base = 1100.0 * pitch
    table = {
        "click": [(base, 0.025)],
        "tab": [(base * 0.8, 0.035), (base * 1.2, 0.045)],
        "open": [(base * 0.5, 0.05), (base * 0.75, 0.05), (base, 0.08)],
        "save": [(base * 0.8, 0.06), (base * 1.2, 0.12)],
        "error": [(base * 0.2, 0.18)],
    }
    return _tone(table[event], square=True, noise=0.02)


def write_wav(path: Path, samples: list[float]) -> None:
    peak = max((abs(value) for value in samples), default=1.0) or 1.0
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, value / peak * 0.8)) * 32767))
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
        path = self._cache / f"{self.theme}-{event}.wav"
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
