from __future__ import annotations

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
    view.steam_root_edit.setText("/tmp/steam")
    view.category_buttons[0].click()
    assert view.settings_stack.currentWidget() is view.general_panel
    view.category_buttons[6].click()
    assert view.settings_stack.currentWidget() is view.support_panel
    assert view.support_panel.isVisible()
    view.save()
    assert view.settings.steam_root == Path("/tmp/steam")


def test_settings_content_starts_at_canonical_vertical_anchor_without_moving_actions(
    qtbot, tmp_path: Path
) -> None:
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)
    view.resize(1530, 808)
    view.show()
    apply_theme(QApplication.instance())
    qtbot.wait(20)

    assert view.settings_scroll.y() == 63
    assert [page.y() for page in (
        view.general_panel,
        view.paths_panel,
        view.cloud_panel,
        view.diagnostics_panel,
    )] == [0, 190, 395, 545]
    assert view.save_button.y() == 755


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
