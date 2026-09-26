"""Real menu sounds and menu music from the player's own trilogy install.

Nothing is redistributed: when a game's save is browsed or opened, the
exact files its main menu uses (``configs/ui/ui_mm_main_c.xml``:
``snd_btn_accept``/``snd_btn_switch`` and ``menu_music``) are read from the
installed game's archives, decoded once with Qt Multimedia and cached as WAV
in the user data directory.  Without an install the synthesized cues in
:mod:`ui.effects` stay in use.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal

from editor.diagnostics import LOGGER_NAME
from editor.platforms import installed_releases, user_data_dir
from editor.releases import release_by_id

from .worker_process import JsonJob

LOGGER = logging.getLogger(f"{LOGGER_NAME}.audio")
AUDIO_VERSION = 1
SAMPLE_RATE = 44_100

# Event → file.  The console menu set is what the Enhanced Editions' main
# menu plays; the inventory cues differ per game.
EVENT_FILES = {
    "click": "sounds/interface/console/menu_accept.ogg",
    "tab": "sounds/interface/console/menu_switch.ogg",
    "hover": "sounds/interface/console/menu_select.ogg",
    "error": "sounds/interface/console/menu_decline.ogg",
    "open": "sounds/interface/inv_open.ogg",
    "save": "sounds/interface/inv_slot.ogg",
}
# ``menu_music`` of each game's main menu; Shadow of Chornobyl stores its
# stereo theme as two mono halves.
MUSIC_FILES = {
    "soc": ("sounds/music/wasteland2_l.ogg", "sounds/music/wasteland2_r.ogg"),
    "clear_sky": ("sounds/music/wasteland2.ogg",),
    "cop": ("sounds/music/menu.ogg",),
}
FAMILIES = frozenset(MUSIC_FILES)


def bundled_audio_dir(family: str) -> Path | None:
    """The menu audio shipped with the app (D4), complete or not at all."""

    meipass = getattr(sys, "_MEIPASS", None)
    base = Path(meipass) if meipass else Path(__file__).resolve().parent.parent
    folder = base / "assets" / "sounds" / "game" / family
    wanted = (*EVENT_FILES.values(), *MUSIC_FILES.get(family, ()))
    if family in MUSIC_FILES and all((folder / name.rsplit("/", 1)[-1]).is_file() for name in wanted):
        return folder
    return None


def install_root(family: str) -> Path | None:
    """An installed game of this family; the original release wins over EE."""

    found: list[tuple[int, Path]] = []
    try:
        games = installed_releases()
    except Exception:
        return None
    for game in games:
        try:
            release = release_by_id(game.release_id)
        except KeyError:
            continue
        if release.family == family and Path(game.install_dir).is_dir():
            found.append((0 if release.edition == "original" else 1, Path(game.install_dir)))
    return min(found)[1] if found else None


def write_pcm_wav(path: Path, frames: bytes, channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with wave.open(str(temp), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames)
    os.replace(temp, path)


def interleave(left: bytes, right: bytes) -> bytes:
    """Two mono 16-bit streams → one stereo stream (shorter one is padded)."""

    count = max(len(left), len(right)) // 2
    left = left.ljust(count * 2, b"\0")
    right = right.ljust(count * 2, b"\0")
    out = bytearray(count * 4)
    out[0::4] = left[0::2]
    out[1::4] = left[1::2]
    out[2::4] = right[0::2]
    out[3::4] = right[1::2]
    return bytes(out)


def extract_files(family: str, root: Path, raw_dir: Path) -> dict[str, str]:
    """Copy this family's menu audio out of the install (``--extract-game-audio``)."""

    from editor.xray_catalog import read_xray_assets

    wanted = (*EVENT_FILES.values(), *MUSIC_FILES[family])
    result: dict[str, str] = {}
    for relative, data in read_xray_assets(root, wanted).items():
        target = raw_dir / relative.rsplit("/", 1)[-1]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        result[relative] = str(target)
    return result


def extract_main(arguments: list[str]) -> int:
    """``--extract-game-audio <family> <install root> <raw dir>``."""

    from .worker_process import emit_result

    try:
        family, root, raw_dir = arguments[:3]
        return emit_result(extract_files(family, Path(root), Path(raw_dir)))
    except Exception:
        return emit_result(None)


class GameAudio(QObject):
    """Prepare and locate cached WAVs for one game family at a time."""

    ready = Signal(str)

    def __init__(self, cache_dir: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache = (cache_dir or user_data_dir() / "sounds") / f"game-v{AUDIO_VERSION}"
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        self._jobs: dict[str, JsonJob] = {}
        self._decoders: list[object] = []
        self._cleanup: dict[str, list[Path]] = {}

    # --- paths --------------------------------------------------------
    def event_path(self, family: str, event: str) -> Path:
        return self._cache / family / f"{event}.wav"

    def music_path(self, family: str) -> Path:
        # One-file themes stay compressed (Qt plays OGG); Shadow of
        # Chornobyl's two mono halves are joined into one stereo WAV.
        suffix = ".wav" if len(MUSIC_FILES.get(family, ())) > 1 else ".ogg"
        return self._cache / family / f"menu-music{suffix}"

    def has_event(self, family: str, event: str) -> bool:
        return family in FAMILIES and self.event_path(family, event).is_file()

    def has_music(self, family: str) -> bool:
        return family in FAMILIES and self.music_path(family).is_file()

    def prepared(self, family: str) -> bool:
        return all(self.has_event(family, event) for event in EVENT_FILES) and self.has_music(family)

    # --- preparation --------------------------------------------------
    def prepare(self, family: str) -> None:
        if family not in FAMILIES or family in self._pending or family in self._failed:
            return
        if self.prepared(family):
            return
        bundled = bundled_audio_dir(family)
        if bundled is not None:
            # Decoding consumes its inputs, so work on copies of the bundle.
            raw = self._cache / family / "raw"
            raw.mkdir(parents=True, exist_ok=True)
            payload: dict[str, str] = {}
            for relative in (*EVENT_FILES.values(), *MUSIC_FILES[family]):
                name = relative.rsplit("/", 1)[-1]
                shutil.copyfile(bundled / name, raw / name)
                payload[relative] = str(raw / name)
            self._pending.add(family)
            self._extracted(family, payload)
            return
        root = install_root(family)
        if root is None:
            LOGGER.info("game audio: no installed %s, synthesized cues stay", family)
            self._failed.add(family)
            return
        LOGGER.info("game audio: extracting %s from %s", family, root)
        self._pending.add(family)
        self._jobs[family] = JsonJob(
            ["--extract-game-audio", family, str(root), str(self._cache / family / "raw")],
            lambda payload: self._extracted(family, payload),
            self,
        )

    def shutdown(self) -> None:
        for job in list(self._jobs.values()):
            job.kill()

    def _extracted(self, family: str, payload: object) -> None:
        self._jobs.pop(family, None)
        files = (
            {str(key): Path(str(value)) for key, value in payload.items()}
            if isinstance(payload, dict)
            else None
        )
        if not files:
            LOGGER.warning("game audio: nothing extracted for %s", family)
            self._pending.discard(family)
            self._failed.add(family)
            return
        jobs: list[tuple[list[Path], Path, int]] = []
        for event, relative in EVENT_FILES.items():
            if relative in files:
                jobs.append(([files[relative]], self.event_path(family, event), 1))
        music = [files[relative] for relative in MUSIC_FILES[family] if relative in files]
        if len(music) == 1:
            target = self.music_path(family)
            os.replace(music[0], target)
        elif music and len(music) == len(MUSIC_FILES[family]):
            jobs.append((music, self.music_path(family), 2))
        self._decode_next(family, jobs, cleanup=[path for path in files.values()])

    def _decode_next(
        self,
        family: str,
        jobs: list[tuple[list[Path], Path, int]],
        cleanup: list[Path] | None = None,
    ) -> None:
        if cleanup is not None:
            self._cleanup[family] = cleanup
        if not jobs:
            for path in self._cleanup.pop(family, ()):
                path.unlink(missing_ok=True)
            self._pending.discard(family)
            LOGGER.info("game audio: %s ready (music=%s)", family, self.has_music(family))
            self.ready.emit(family)
            return
        sources, target, channels = jobs[0]
        halves: list[bytes] = []

        def decoded(pcm: bytes | None) -> None:
            if pcm is None:
                self._decode_next(family, jobs[1:])
                return
            halves.append(pcm)
            if len(halves) < len(sources):
                self._decode(sources[len(halves)], 1 if len(sources) > 1 else channels, decoded)
                return
            frames = interleave(halves[0], halves[1]) if len(halves) == 2 else halves[0]
            try:
                write_pcm_wav(target, frames, channels)
            except OSError:
                pass
            self._decode_next(family, jobs[1:])

        self._decode(sources[0], 1 if len(sources) > 1 else channels, decoded)

    def _decode(self, source: Path, channels: int, callback) -> None:
        try:
            from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
        except Exception:
            callback(None)
            return
        decoder = QAudioDecoder(self)
        audio_format = QAudioFormat()
        audio_format.setSampleRate(SAMPLE_RATE)
        audio_format.setChannelCount(channels)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        decoder.setAudioFormat(audio_format)
        decoder.setSource(QUrl.fromLocalFile(str(source)))
        chunks: list[bytes] = []
        self._decoders.append(decoder)

        def finish(ok: bool) -> None:
            if decoder in self._decoders:
                self._decoders.remove(decoder)
                decoder.deleteLater()
                callback(b"".join(chunks) if ok and chunks else None)

        decoder.bufferReady.connect(lambda: chunks.append(bytes(decoder.read().data())))
        decoder.finished.connect(lambda: finish(True))
        decoder.error.connect(lambda _error: finish(False))
        decoder.start()


__all__ = [
    "EVENT_FILES",
    "FAMILIES",
    "MUSIC_FILES",
    "GameAudio",
    "extract_main",
    "install_root",
    "interleave",
    "write_pcm_wav",
]
