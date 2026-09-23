from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.settings import PathSettings
from ui.settings_view import SettingsView


def test_settings_reference_has_seven_categories_and_safety_panels(qtbot, tmp_path: Path) -> None:
    view = SettingsView(PathSettings(), settings_path=tmp_path / "settings.json")
    qtbot.addWidget(view)

    assert view.objectName() == "settingsView"
    assert len(view.category_buttons) == 7
    assert [button.text() for button in view.category_buttons] == [
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
        "uncertain" in label.text().casefold()
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
