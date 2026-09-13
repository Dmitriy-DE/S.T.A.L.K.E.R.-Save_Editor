from __future__ import annotations

from pathlib import Path

from editor.platforms import (
    APP_DIR_NAME,
    HELPER_ENV,
    backup_dirs,
    discover_helper,
    legacy_data_dir,
    user_data_dir,
)


def test_linux_user_data_dir_uses_xdg_data_home_with_unicode_and_spaces(tmp_path: Path) -> None:
    xdg = tmp_path / "Данные пользователя" / "editor files"

    result = user_data_dir(
        system="Linux",
        environ={"XDG_DATA_HOME": str(xdg)},
        home=tmp_path / "home",
    )

    assert result == xdg / APP_DIR_NAME


def test_linux_user_data_dir_defaults_to_home_local_share(tmp_path: Path) -> None:
    home = tmp_path / "home"

    assert user_data_dir(system="Linux", environ={}, home=home) == home / ".local" / "share" / APP_DIR_NAME


def test_windows_user_data_dir_uses_appdata_before_localappdata(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    local = tmp_path / "AppData" / "Local"

    assert user_data_dir(
        system="Windows",
        environ={"APPDATA": str(appdata), "LOCALAPPDATA": str(local)},
        home=tmp_path / "home",
    ) == appdata / APP_DIR_NAME


def test_windows_user_data_dir_falls_back_to_localappdata_and_then_home(tmp_path: Path) -> None:
    local = tmp_path / "AppData" / "Local"
    home = tmp_path / "home"

    assert user_data_dir(system="Windows", environ={"LOCALAPPDATA": str(local)}, home=home) == local / APP_DIR_NAME
    assert user_data_dir(system="Windows", environ={}, home=home) == home / "AppData" / "Roaming" / APP_DIR_NAME


def test_legacy_directory_is_reported_without_mutation_or_migration(tmp_path: Path) -> None:
    home = tmp_path / "home"
    legacy = legacy_data_dir(home=home)
    legacy_backup = legacy / "backups" / "old copy.sav"
    legacy_backup.parent.mkdir(parents=True)
    legacy_backup.write_bytes(b"legacy")

    dirs = backup_dirs(system="Linux", environ={}, home=home)

    assert legacy == home / APP_DIR_NAME
    assert legacy_backup.read_bytes() == b"legacy"
    assert legacy / "backups" in dirs
    assert dirs[0] == home / ".local" / "share" / APP_DIR_NAME / "backups"


def test_discover_helper_uses_explicit_unicode_path_first(tmp_path: Path) -> None:
    helper = tmp_path / "папка с пробелами" / "SteamCloudFileManager.AppImage"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"helper")
    helper.chmod(0o755)

    found = discover_helper(
        system="Linux",
        environ={HELPER_ENV: str(helper)},
        home=tmp_path / "home",
    )

    assert found == helper


def test_discover_helper_returns_none_when_missing(tmp_path: Path) -> None:
    assert discover_helper(system="Linux", environ={}, home=tmp_path) is None


def test_discover_helper_rejects_non_executable_linux_file(tmp_path: Path) -> None:
    helper = tmp_path / "Downloads" / "SteamCloudFileManager.AppImage"
    helper.parent.mkdir()
    helper.write_bytes(b"helper")
    helper.chmod(0o644)

    assert discover_helper(system="Linux", environ={}, home=tmp_path) is None


def test_discover_helper_finds_windows_exe_with_neighbor_dlls(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    helper = downloads / "SteamCloudFileManager.exe"
    helper.write_bytes(b"MZ")
    (downloads / "steam_api64.dll").write_bytes(b"dll")

    found = discover_helper(system="Windows", environ={}, home=tmp_path)

    assert found == helper


def test_discover_helper_ignores_non_exe_windows_candidate(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "SteamCloudFileManager.AppImage").write_bytes(b"helper")

    assert discover_helper(system="Windows", environ={}, home=tmp_path) is None
