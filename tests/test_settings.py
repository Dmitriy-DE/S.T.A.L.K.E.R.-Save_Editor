from __future__ import annotations

import json
from pathlib import Path

import pytest

from editor.service import EditorService
from editor.settings import (
    SETTINGS_SCHEMA_VERSION,
    PathSettings,
    load_settings,
    missing_manual_paths,
    save_settings,
    search_paths_for_settings,
)

pytest.importorskip("PySide6")

from ui.main_window import MainWindow
from ui.settings_view import SettingsView


def test_existing_manual_save_root_has_priority_over_automatic_search(
    tmp_path: Path,
) -> None:
    manual = tmp_path / "manual saves"
    automatic = tmp_path / "automatic saves"
    manual.mkdir()
    automatic.mkdir()
    settings = PathSettings(save_roots=(("stalker2", manual),))
    calls: list[str] = []

    result = search_paths_for_settings(
        "stalker2",
        settings,
        automatic_fn=lambda game_id: calls.append(game_id) or (automatic,),
    )

    assert result == (manual,)
    assert calls == []


def test_missing_manual_path_is_reported_and_automatic_search_returns(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "removed saves"
    automatic = tmp_path / "automatic saves"
    automatic.mkdir()
    settings = PathSettings(save_roots=(("stalker2", missing),))

    result = search_paths_for_settings(
        "stalker2", settings, automatic_fn=lambda _game_id: (automatic,)
    )

    assert result == (automatic,)
    assert missing_manual_paths(settings) == (missing,)


def test_settings_round_trip_uses_versioned_json(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings = PathSettings(
        steam_root=tmp_path / "Steam",
        game_roots=(("cop", tmp_path / "Call of Pripyat"),),
        save_roots=(("soc", tmp_path / "Shadow saves"),),
        catalog_roots=(("stalker2", tmp_path / "Zone Kit"),),
    )

    assert save_settings(settings, path=settings_path) == settings_path
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SETTINGS_SCHEMA_VERSION
    loaded = load_settings(path=settings_path)

    assert loaded.settings == settings
    assert loaded.error is None


def test_catalog_root_is_separate_from_game_and_save_roots(tmp_path: Path) -> None:
    catalog = tmp_path / "Zone Kit"
    settings = PathSettings().with_catalog_root("stalker2", catalog)

    assert settings.catalog_root("stalker2") == catalog
    assert settings.game_root("stalker2") is None
    assert settings.save_root("stalker2") is None
    assert catalog in settings.manual_paths()


def test_settings_accept_release_specific_manual_roots_and_legacy_family_lookup(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    enhanced = tmp_path / "enhanced saves"
    enhanced.mkdir()
    settings = PathSettings(save_roots=(("stalker-soc-ee", enhanced),))

    save_settings(settings, path=settings_path)
    loaded = load_settings(path=settings_path)

    assert loaded.settings.save_root("stalker-soc-ee") == enhanced
    assert loaded.settings.save_root("stalker-soc") is None

    legacy = PathSettings(save_roots=(("soc", enhanced),))
    assert legacy.save_root("stalker-soc") == enhanced


def test_missing_settings_file_is_empty_without_error(tmp_path: Path) -> None:
    loaded = load_settings(path=tmp_path / "missing.json")

    assert loaded.settings == PathSettings()
    assert loaded.error is None


def test_broken_or_foreign_settings_are_empty_and_nonfatal(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{broken", encoding="utf-8")
    broken = load_settings(path=settings_path)
    assert broken.settings == PathSettings()
    assert broken.error is not None
    assert "пуст" in broken.error.casefold()

    settings_path.write_text(
        json.dumps({"version": 99, "paths": {"save": "/tmp/foreign"}}),
        encoding="utf-8",
    )
    foreign = load_settings(path=settings_path)
    assert foreign.settings == PathSettings()
    assert foreign.error is not None
    assert "верси" in foreign.error.casefold()


def test_settings_view_explains_missing_path_and_can_persist_selection(
    qtbot, tmp_path: Path
) -> None:
    missing = tmp_path / "gone"
    selected = tmp_path / "selected saves"
    selected.mkdir()
    settings_path = tmp_path / "settings.json"
    view = SettingsView(
        PathSettings(save_roots=(("stalker2", missing),)),
        settings_path=settings_path,
    )
    qtbot.addWidget(view)

    assert str(missing) in view.warning_label.text()
    assert view.found_all_label.objectName() == "discoveryResults"
    assert "palette(mid)" not in view.found_all_label.styleSheet()
    # The Steam root and the explicit S2 resource root are independent manual
    # fields; a Zone Kit is metadata input, not a save-write destination.
    view.steam_root_edit.setText(str(selected))
    view.catalog_root_edit.setText(str(selected))
    with qtbot.waitSignal(view.settings_changed, timeout=1_000):
        view.save()

    loaded = load_settings(path=settings_path).settings
    assert loaded.steam_root == selected
    assert loaded.catalog_root("stalker2") == selected


def test_settings_view_emits_environment_check_request(qtbot, tmp_path: Path) -> None:
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.environment_check_requested, timeout=1_000):
        view.environment_check_button.click()


def test_main_window_discovers_from_loaded_manual_save_root(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    manual = tmp_path / "manual saves"
    manual.mkdir()
    (manual / "manual.sav").write_bytes(synthetic_save)
    settings_path = tmp_path / "settings.json"
    save_settings(PathSettings(save_roots=(("stalker2", manual),)), path=settings_path)

    window = MainWindow(EditorService(), settings_path=settings_path)
    qtbot.addWidget(window)
    qtbot.waitUntil(lambda: window.discovery_controller._worker is None, timeout=5_000)

    discovered = [slot.path for slot in window.discovery_controller.slots]
    assert manual / "manual.sav" in discovered
    assert window.discovery_controller.searched_paths[0] == manual
