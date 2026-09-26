from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from editor import diagnostics
from editor.platforms import InstalledGame
from editor.releases import official_releases


def _release():
    return next(release for release in official_releases() if release.family != "stalker2")


def _installed_game(tmp_path: Path, release) -> InstalledGame:
    library = tmp_path / "steam-library"
    steamapps = library / "steamapps"
    install = steamapps / "common" / "Synthetic Game"
    steamapps.mkdir(parents=True)
    install.mkdir(parents=True)
    manifest = steamapps / f"appmanifest_{release.app_ids[0]}.acf"
    manifest.write_text(
        f'"AppState" {{ "appid" "{release.app_ids[0]}" '
        '"buildid" "123456" "installdir" "Synthetic Game" }',
        encoding="utf-8",
    )
    return InstalledGame(
        game_id=release.family,
        app_id=release.app_ids[0],
        edition=release.edition,
        library_root=library,
        install_dir=install,
    )


def _check(name: str, *args):
    return getattr(diagnostics, name)(*args)


def test_check_record_and_report_format_are_stable() -> None:
    result = diagnostics.Check("Данные", "Каталог", "ok", "Готов", "")

    assert result.group == "Данные"
    assert result.name == "Каталог"
    assert result.status == "ok"
    report = diagnostics.format_report([result])
    assert "Данные" in report
    assert "Каталог" in report
    assert "Готов" in report


def test_game_installation_check_reports_redacted_path_and_missing_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _release()
    installed = _installed_game(tmp_path, release)
    monkeypatch.setattr(diagnostics, "_installed_releases", lambda: (installed,))
    monkeypatch.setattr(diagnostics.Path, "home", classmethod(lambda _cls: tmp_path))

    result = _check("check_game_installation", release)

    assert result.status == "ok"
    assert "~/steam-library" in result.detail
    assert str(tmp_path) not in result.detail

    monkeypatch.setattr(diagnostics, "_installed_releases", lambda: ())
    assert _check("check_game_installation", release).status == "warn"
    monkeypatch.setattr(
        diagnostics,
        "_installed_releases",
        lambda: (_ for _ in ()).throw(OSError("synthetic discovery failure")),
    )
    assert _check("check_game_installation", release).status == "fail"


def test_game_buildid_check_reports_present_and_missing_buildid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _release()
    installed = _installed_game(tmp_path, release)
    monkeypatch.setattr(diagnostics, "_installed_releases", lambda: (installed,))

    result = _check("check_game_buildid", release)

    assert result.status == "ok"
    assert "123456" in result.detail
    (installed.library_root / "steamapps" / f"appmanifest_{release.app_ids[0]}.acf").write_text(
        '"AppState" { "appid" "1" }', encoding="utf-8"
    )
    assert _check("check_game_buildid", release).status == "warn"
    monkeypatch.setattr(
        diagnostics,
        "_installed_releases",
        lambda: (_ for _ in ()).throw(OSError("synthetic discovery failure")),
    )
    assert _check("check_game_buildid", release).status == "fail"


@pytest.mark.parametrize("function", ["check_game_saves_folder", "check_game_save_count"])
def test_game_save_checks_report_available_and_missing_folders(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    function: str,
) -> None:
    release = _release()
    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    (save_dir / "slot.sav").write_bytes(b"synthetic marker; never parsed")
    monkeypatch.setattr(diagnostics, "_save_directories", lambda _release: (save_dir,))

    result = _check(function, release)

    assert result.status == "ok"
    assert "1" in result.detail or "saves" in result.detail
    monkeypatch.setattr(diagnostics, "_save_directories", lambda _release: ())
    assert _check(function, release).status == "warn"
    monkeypatch.setattr(
        diagnostics,
        "_save_directories",
        lambda _release: (_ for _ in ()).throw(OSError("synthetic folder failure")),
    )
    assert _check(function, release).status == "fail"


def test_data_directory_check_reports_writable_and_unavailable_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_dir = tmp_path / "app-data"
    data_dir.mkdir()
    monkeypatch.setattr(diagnostics, "user_data_dir", lambda: data_dir)

    assert _check("check_data_directory").status == "ok"
    monkeypatch.setattr(diagnostics, "user_data_dir", lambda: tmp_path / "missing")
    assert _check("check_data_directory").status == "warn"
    monkeypatch.setattr(
        diagnostics,
        "user_data_dir",
        lambda: (_ for _ in ()).throw(OSError("synthetic data failure")),
    )
    assert _check("check_data_directory").status == "fail"


def test_icons_check_reports_assets_and_missing_icons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "assets" / "icons").mkdir(parents=True)
    (tmp_path / "web" / "icons").mkdir(parents=True)
    (tmp_path / "assets" / "icons" / "desktop.png").write_bytes(b"png")
    (tmp_path / "web" / "icons" / "web.png").write_bytes(b"png")
    monkeypatch.setattr(diagnostics, "PROJECT_ROOT", tmp_path)

    assert _check("check_icons").status == "ok"
    (tmp_path / "web" / "icons" / "web.png").unlink()
    assert _check("check_icons").status == "fail"


def test_official_names_check_reports_valid_and_missing_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "catalog_names.json"
    monkeypatch.setattr(diagnostics, "OFFICIAL_NAMES_PATH", path)
    path.write_text(
        json.dumps(
            {
                "releases": {
                    family: {"items": {"bandage": {"en": "Bandage"}}}
                    for family in ("soc", "clear_sky", "cop")
                }
            }
        ),
        encoding="utf-8",
    )

    assert _check("check_official_names").status == "ok"
    path.write_text("{}", encoding="utf-8")
    assert _check("check_official_names").status == "fail"


def test_s2_schema_check_reports_supported_and_invalid_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "s2_items.json"
    monkeypatch.setattr(diagnostics, "S2_ITEMS_PATH", path)
    path.write_text(json.dumps({"schema_version": 2, "items": {"item": {}}}), encoding="utf-8")

    assert _check("check_s2_schema").status == "ok"
    path.write_text(json.dumps({"schema_version": 99, "items": {}}), encoding="utf-8")
    assert _check("check_s2_schema").status == "fail"


def test_sound_cache_check_reports_complete_and_missing_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    family = "soc"
    cache = tmp_path / "sounds" / "game-v1"
    monkeypatch.setattr(diagnostics, "_sound_cache_root", lambda: cache)
    assert _check("check_sound_cache", family).status == "warn"

    game_cache = cache / family
    game_cache.mkdir(parents=True)
    for name in diagnostics._SOUND_CACHE_FILES[family]:
        (game_cache / name).write_bytes(b"cached audio")
    assert _check("check_sound_cache", family).status == "ok"
    monkeypatch.setattr(
        diagnostics,
        "_sound_cache_root",
        lambda: (_ for _ in ()).throw(OSError("synthetic cache failure")),
    )
    assert _check("check_sound_cache", family).status == "fail"


def test_game_audio_source_check_reports_present_and_missing_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = _release()
    installed = _installed_game(tmp_path, release)
    monkeypatch.setattr(diagnostics, "_installed_releases", lambda: (installed,))
    monkeypatch.setattr(diagnostics, "read_xray_asset", lambda *_args: b"audio")

    assert _check("check_game_audio_source", release.family).status == "ok"
    monkeypatch.setattr(diagnostics, "read_xray_asset", lambda *_args: None)
    assert _check("check_game_audio_source", release.family).status == "fail"


def test_s2_audio_source_check_is_reported_as_unsupported() -> None:
    assert _check("check_game_audio_source", "stalker2").status == "warn"


def test_media_error_and_output_device_checks_use_registered_qt_free_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diagnostics, "_last_media_error", None)
    assert _check("check_last_media_error").status == "ok"
    monkeypatch.setattr(diagnostics, "_last_media_error", "Decoder error")
    assert _check("check_last_media_error").status == "fail"

    monkeypatch.setattr(diagnostics, "_output_device", "Default Speakers")
    assert _check("check_output_device").status == "ok"
    monkeypatch.setattr(diagnostics, "_output_device", None)
    assert _check("check_output_device").status == "warn"


def test_update_manifest_check_reports_available_and_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        diagnostics,
        "UpdateClient",
        lambda **_kwargs: SimpleNamespace(check=lambda: SimpleNamespace(state="current")),
    )
    assert _check("check_update_manifest").status == "ok"
    monkeypatch.setattr(
        diagnostics,
        "UpdateClient",
        lambda **_kwargs: SimpleNamespace(check=lambda: SimpleNamespace(state="unavailable")),
    )
    assert _check("check_update_manifest").status == "warn"
    monkeypatch.setattr(
        diagnostics,
        "UpdateClient",
        lambda **_kwargs: SimpleNamespace(check=lambda: SimpleNamespace(state="invalid")),
    )
    assert _check("check_update_manifest").status == "fail"


@pytest.mark.parametrize(
    "function",
    ["check_pkexec", "check_apt_get", "check_xdg_open"],
)
def test_update_tool_checks_report_present_and_missing_commands(
    monkeypatch: pytest.MonkeyPatch, function: str
) -> None:
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _command: "/usr/bin/tool")
    assert _check(function).status == "ok"
    monkeypatch.setattr(diagnostics.shutil, "which", lambda _command: None)
    assert _check(function).status == "warn"
    monkeypatch.setattr(
        diagnostics.shutil,
        "which",
        lambda _command: (_ for _ in ()).throw(OSError("synthetic path failure")),
    )
    assert _check(function).status == "fail"


def test_installation_type_check_reports_detected_and_unknown_types(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        diagnostics,
        "detect_installation",
        lambda: SimpleNamespace(kind="portable"),
    )
    assert _check("check_installation_type").status == "ok"

    def unknown_installation():
        raise RuntimeError("not installed")

    monkeypatch.setattr(diagnostics, "detect_installation", unknown_installation)
    assert _check("check_installation_type").status == "warn"
    monkeypatch.setattr(
        diagnostics,
        "detect_installation",
        lambda: SimpleNamespace(kind="unknown"),
    )
    assert _check("check_installation_type").status == "fail"


def test_steam_library_check_reports_loadable_and_missing_library(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    library = tmp_path / "libsteam_api.so"
    library.write_bytes(b"synthetic library marker")
    monkeypatch.setattr(diagnostics, "_find_steam_api_library", lambda: library)
    monkeypatch.setattr(diagnostics.ctypes, "CDLL", lambda _path: object())

    assert _check("check_steam_api_library").status == "ok"
    monkeypatch.setattr(diagnostics, "_find_steam_api_library", lambda: None)
    assert _check("check_steam_api_library").status == "warn"
    monkeypatch.setattr(diagnostics, "_find_steam_api_library", lambda: library)
    monkeypatch.setattr(
        diagnostics.ctypes,
        "CDLL",
        lambda _path: (_ for _ in ()).throw(OSError("synthetic loader failure")),
    )
    assert _check("check_steam_api_library").status == "fail"


def test_steam_running_check_reports_running_and_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "_steam_process_running", lambda: True)
    assert _check("check_steam_running").status == "ok"
    monkeypatch.setattr(diagnostics, "_steam_process_running", lambda: False)
    assert _check("check_steam_running").status == "warn"
    monkeypatch.setattr(
        diagnostics,
        "_steam_process_running",
        lambda: (_ for _ in ()).throw(OSError("synthetic process failure")),
    )
    assert _check("check_steam_running").status == "fail"


def test_kraken_decode_and_encode_checks_report_available_and_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        diagnostics.codec,
        "load_decoder",
        lambda: SimpleNamespace(decompress=lambda stream, _size: stream[2:]),
    )
    assert _check("check_kraken_decode").status == "ok"
    monkeypatch.setattr(diagnostics.codec, "load_decoder", lambda: (_ for _ in ()).throw(RuntimeError("missing")))
    assert _check("check_kraken_decode").status == "fail"

    monkeypatch.setattr(diagnostics.codec, "load_encoder", lambda: SimpleNamespace(compress=lambda *_: b"encoded"))
    assert _check("check_kraken_encode").status == "ok"
    monkeypatch.setattr(diagnostics.codec, "load_encoder", lambda: (_ for _ in ()).throw(RuntimeError("missing")))
    assert _check("check_kraken_encode").status == "warn"
    monkeypatch.setattr(
        diagnostics.codec,
        "load_encoder",
        lambda: SimpleNamespace(compress=lambda *_: b"encoded"),
    )
    monkeypatch.setattr(
        diagnostics.codec,
        "compress",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("synthetic encode failure")),
    )
    assert _check("check_kraken_encode").status == "fail"


def test_kraken_decode_check_executes_a_synthetic_stored_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = b"Save Editor Kraken decoder probe\x00" * 32
    calls: list[tuple[bytes, int]] = []

    class Decoder:
        def decompress(self, stream: bytes, unpacked_size: int) -> bytes:
            calls.append((stream, unpacked_size))
            return raw if stream == b"\xCC\x06" + raw and unpacked_size == len(raw) else b""

    monkeypatch.setattr(diagnostics.codec, "load_decoder", lambda: Decoder())

    assert _check("check_kraken_decode").status == "ok"
    assert calls == [(b"\xCC\x06" + raw, len(raw))]

    monkeypatch.setattr(
        diagnostics.codec,
        "load_decoder",
        lambda: SimpleNamespace(decompress=lambda _stream, _size: b""),
    )
    assert _check("check_kraken_decode").status == "fail"


def test_xray_lzo_check_reports_roundtrip_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "lzo1x_compress", lambda raw: raw)
    monkeypatch.setattr(diagnostics, "lzo1x_decompress", lambda packed, size: packed[:size])
    assert _check("check_xray_lzo").status == "ok"
    monkeypatch.setattr(diagnostics, "lzo1x_decompress", lambda _packed, _size: b"wrong")
    assert _check("check_xray_lzo").status == "fail"


def test_child_peek_check_reports_response_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "_run_peek", lambda: True)
    assert _check("check_child_peek").status == "ok"
    monkeypatch.setattr(diagnostics, "_run_peek", lambda: False)
    assert _check("check_child_peek").status == "fail"


def test_peek_probe_gets_json_from_a_temporary_synthetic_file() -> None:
    assert diagnostics._run_peek()


def test_environment_report_is_attached_to_redacted_log_bundle(
    tmp_path: Path,
) -> None:
    (tmp_path / diagnostics.LOG_FILENAME).write_text("operation=inspect\n", encoding="utf-8")
    report = "Steam: OK\nUser path: /home/private-user/Saves"

    payload = diagnostics.collect_log_bundle(tmp_path, environment_report=report)
    contents = diagnostics.gzip.decompress(payload).decode("utf-8")

    assert "operation=inspect" in contents
    assert "Steam: OK" in contents
    assert "/home/private-user" not in contents


def test_run_checks_returns_only_card_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "_installed_releases", lambda: ())
    monkeypatch.setattr(diagnostics, "_save_directories", lambda _release_id: ())
    groups = {
        "check_game_installation": "Игры",
        "check_game_buildid": "Игры",
        "check_game_saves_folder": "Игры",
        "check_game_save_count": "Игры",
        "check_data_directory": "Данные",
        "check_icons": "Данные",
        "check_official_names": "Данные",
        "check_s2_schema": "Данные",
        "check_sound_cache": "Звук",
        "check_game_audio_source": "Звук",
        "check_last_media_error": "Звук",
        "check_output_device": "Звук",
        "check_update_manifest": "Обновления",
        "check_pkexec": "Обновления",
        "check_apt_get": "Обновления",
        "check_xdg_open": "Обновления",
        "check_installation_type": "Обновления",
        "check_steam_api_library": "Steam",
        "check_steam_running": "Steam",
        "check_kraken_decode": "Кодеки",
        "check_kraken_encode": "Кодеки",
        "check_xray_lzo": "Кодеки",
        "check_child_peek": "Дочерние задачи",
    }
    for name, group in groups.items():
        def record(*_args, _group=group, _name=name, **_kwargs):
            return diagnostics.Check(_group, _name, "ok", "fixture", "")

        monkeypatch.setattr(diagnostics, name, record)

    results = diagnostics.run_checks()

    assert results
    assert {result.group for result in results} == {
        "Игры",
        "Данные",
        "Звук",
        "Обновления",
        "Steam",
        "Кодеки",
        "Дочерние задачи",
    }
    assert Counter(result.group for result in results) == {
        "Игры": 4 * len(official_releases()),
        "Данные": 4,
        "Звук": 2 * len(diagnostics._SOUND_FAMILIES) + 2,
        "Обновления": 5,
        "Steam": 2,
        "Кодеки": 3,
        "Дочерние задачи": 1,
    }
