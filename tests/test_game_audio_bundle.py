"""The trilogy menu audio ships with the app (D4) and is used before the game."""

from __future__ import annotations

from pathlib import Path

import pytest

import ui.game_audio as game_audio


@pytest.mark.parametrize("family", sorted(game_audio.FAMILIES))
def test_every_family_has_a_complete_bundled_set(family: str) -> None:
    folder = game_audio.bundled_audio_dir(family)
    assert folder is not None
    for relative in (*game_audio.EVENT_FILES.values(), *game_audio.MUSIC_FILES[family]):
        assert (folder / relative.rsplit("/", 1)[-1]).stat().st_size > 0


def test_prepare_uses_the_bundle_without_an_installed_game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, dict[str, str]] = {}
    monkeypatch.setattr(game_audio, "install_root", lambda _family: pytest.fail("the installed game must not be needed"))
    monkeypatch.setattr(game_audio.GameAudio, "_extracted", lambda self, family, payload: seen.setdefault(family, payload))
    audio = game_audio.GameAudio(cache_dir=tmp_path)
    audio.prepare("cop")
    files = [Path(path) for path in seen["cop"].values()]
    assert files and all(path.is_file() and tmp_path in path.parents for path in files)
    # The bundle itself is copied, never consumed.
    assert game_audio.bundled_audio_dir("cop") is not None


def test_unknown_family_has_no_bundle() -> None:
    assert game_audio.bundled_audio_dir("stalker2") is None
