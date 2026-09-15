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
    )

    assert save_settings(settings, path=settings_path) == settings_path
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SETTINGS_SCHEMA_VERSION
    loaded = load_settings(path=settings_path)

    assert loaded.settings == settings
    assert loaded.error is None


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
    view.save_root_edit.setText(str(selected))
    with qtbot.waitSignal(view.settings_changed, timeout=1_000):
        view.save()

    assert load_settings(path=settings_path).settings.save_root("stalker2") == selected


def test_settings_view_lists_original_and_enhanced_release_choices(
    qtbot, tmp_path: Path
) -> None:
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)

    ids = [view.game_combo.itemData(index) for index in range(view.game_combo.count())]

    assert "stalker-soc" in ids
    assert "stalker-soc-ee" in ids


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
    qtbot.waitUntil(window.save_slots_view.refresh_button.isEnabled, timeout=5_000)

    discovered = [slot.path for slot in window.save_slots_view.slots]
    assert manual / "manual.sav" in discovered
    assert window.save_slots_view.searched_paths[0] == manual
