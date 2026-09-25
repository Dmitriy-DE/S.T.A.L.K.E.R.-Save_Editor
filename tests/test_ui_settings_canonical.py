from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from editor.settings import PathSettings
from ui.settings_view import SettingsView
from ui.theme import apply_theme


def test_settings_reference_has_seven_categories_and_safety_panels(qtbot, tmp_path: Path) -> None:
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)

    assert view.objectName() == "settingsView"
    assert len(view.category_buttons) == 7
    assert [button.accessibleName() for button in view.category_buttons] == [
        "ОБЩИЕ",
        "ПУТИ И АВТОПОИСК",
        "РЕЗЕРВНЫЕ КОПИИ",
        "STEAM CLOUD",
        "ОБНОВЛЕНИЯ И ДИАГНОСТИКА",
        "ИНТЕРФЕЙС",
        "ПОДДЕРЖКА",
    ]
    assert view.general_panel.objectName() == "generalSettingsPanel"
    assert view.paths_panel.objectName() == "pathsSettingsPanel"
    assert view.cloud_panel.objectName() == "cloudSettingsPanel"
    assert view.diagnostics_panel.objectName() == "diagnosticsSettingsPanel"
    assert view.save_button.text().startswith("СОХРАНИТЬ")
    assert any(
        "не подтвердил запись" in label.text().casefold()
        for label in view.cloud_panel.findChildren(type(view.safety_labels[0]))
    )
    assert view.core_safety_read_only is True


def test_settings_category_navigation_keeps_path_fields_and_save_semantics(qtbot, tmp_path: Path) -> None:
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)
    view.show()
    view.category_buttons[1].click()
    assert view.settings_stack.currentWidget() is view.paths_panel
    assert view.paths_panel.isVisible()
    # An absolute path on every OS; "/tmp/steam" has no drive on Windows.
    steam_root = tmp_path / "steam"
    view.steam_root_edit.setText(str(steam_root))
    view.category_buttons[0].click()
    assert view.settings_stack.currentWidget() is view.general_panel
    view.category_buttons[6].click()
    assert view.settings_stack.currentWidget() is view.support_panel
    assert view.support_panel.isVisible()
    view.save()
    assert view.settings.steam_root == steam_root


def test_settings_content_starts_at_canonical_vertical_anchor_without_moving_actions(
    qtbot, tmp_path: Path
) -> None:
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)
    view.resize(1530, 808)
    view.show()
    apply_theme(QApplication.instance())
    qtbot.wait(20)

    # Font metrics differ by a pixel between Linux and Windows.
    assert abs(view.settings_scroll.y() - 63) <= 2
    pages = (
        view.general_panel,
        view.paths_panel,
        view.cloud_panel,
        view.diagnostics_panel,
    )
    assert pages[0].y() == 0
    # Panels are stacked in order and never overlap (heights follow fonts).
    for upper, lower in pairwise(pages):
        assert lower.y() >= upper.y() + upper.height()
    assert abs(view.save_button.y() - 755) <= 2


def test_settings_panel_headers_and_path_controls_fit_without_overlap(qtbot, tmp_path: Path) -> None:
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)
    view.resize(1530, 808)
    view.show()
    apply_theme(QApplication.instance())
    qtbot.wait(20)

    for panel in (
        view.general_panel,
        view.paths_panel,
        view.cloud_panel,
        view.diagnostics_panel,
    ):
        header = panel.findChild(type(view.general_panel), "sectionHeader")
        assert header is not None
        assert header.x() <= 1
        assert header.y() <= 1
    for edit in (view.steam_root_edit, view.catalog_root_edit):
        row = edit.parentWidget()
        assert edit.y() >= 0
        assert edit.y() + edit.height() <= row.height()


def test_backup_path_row_has_truthful_open_action_and_status(qtbot, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("ui.settings_view.backup_dirs", lambda: (tmp_path,))
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)
    opened: list[bool] = []
    view.backup_folder_requested.connect(lambda: opened.append(True))

    assert view.backup_path_button.isEnabled()
    assert view.backup_path_status.text() == "● ГОТОВО"
    view.backup_path_button.click()
    assert opened == [True]


def test_language_change_offers_restart_in_the_chosen_language(qtbot, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from editor import i18n

    monkeypatch.delenv("STALKER_EDITOR_LANG", raising=False)
    monkeypatch.setenv("STALKER_EDITOR_PREFERENCES", str(tmp_path / "preferences.json"))
    i18n.set_language("ru")
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)
    restarts: list[bool] = []
    view.restart_requested.connect(lambda: restarts.append(True))

    view.language_combo.setCurrentIndex(view.language_combo.findData("uk"))

    prompt = view.findChild(QMessageBox, "languageRestartPrompt")
    assert prompt is not None and prompt.isVisible()
    assert prompt.text() == "Мова зміниться після перезапуску. Перезапустити зараз?"
    assert not view.restart_button.isHidden()
    restart = next(b for b in prompt.buttons() if prompt.buttonRole(b) == QMessageBox.ButtonRole.AcceptRole)
    restart.click()
    assert restarts == [True]

    # Picking the language already in use needs no restart and no prompt.
    view.language_combo.setCurrentIndex(view.language_combo.findData("ru"))
    assert view.restart_button.isHidden()
    i18n.set_language("ru")
