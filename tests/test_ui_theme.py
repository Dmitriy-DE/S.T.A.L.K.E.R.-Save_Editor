from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from editor.service import EditorService
from save_format import inspect_save
from ui import theme
from ui.main_window import LocalSnapshot, MainWindow
from ui.theme import COLORS, apply_theme, stylesheet


def test_stalker_shell_exposes_zone_navigation_and_empty_metadata(qtbot) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    assert window.app_title.text() == "S.T.A.L.K.E.R. Save Editor"
    assert window.ui_hint.text() == "S2 / SAVE WORKBENCH"
    assert window.launcher_button.text() == "← БИБЛИОТЕКА"
    assert window.version_badge.text().startswith("v")
    assert window.file_source_badge.text() == "ФАЙЛ НЕ ВЫБРАН"
    assert window.meta_filename.text() == "Сейв не выбран"
    assert window.integrity_badge.text() == "CRC-32: —"
    assert window.format_badge.text() == "ФОРМАТ: —"
    assert window.tabs.tabBar().isHidden()
    assert window.sidebar.objectName() == "sidebar"
    assert [button.text() for button in window.nav_buttons] == [
        "Обзор",
        "Инвентарь",
        "Изменения",
        "Резервные копии",
        "Steam Cloud",
        "Найденные сейвы",
        "Настройки",
        "Оборудование",
    ]
    assert COLORS["bg_base"] in QApplication.instance().styleSheet()

    qtbot.mouseClick(window.nav_buttons[1], Qt.MouseButton.LeftButton)
    assert window.tabs.currentIndex() == 1
    assert window.nav_buttons[1].isChecked()


def test_stalker_shell_metadata_tracks_real_snapshot(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    source = tmp_path / "локальный.sav"
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    window._render_snapshot(
        LocalSnapshot(path=source, data=synthetic_save, info=info)
    )

    assert window.file_source_badge.text() == "ЛОКАЛЬНЫЙ ФАЙЛ"
    assert window.meta_filename.text() == source.name
    assert f"SHA {info.sha256[:12]}" in window.meta_details.text()
    assert window.integrity_badge.text() == "CRC-32: PASS"
    assert window.format_badge.text() == "UE5 GVAS: НЕ ПОДТВЕРЖДЁН"
    assert window.money_card_value.text() == "100"
    assert window.inventory_card_value.text() == "2"
    assert window.location_card_value.text() == "—"
    assert window.time_card_value.text() == "—"
    assert "экспериментальное" in window.support_label.text()


def test_apply_theme_does_not_reconfigure_the_application_twice() -> None:
    class ThemeProbe:
        def __init__(self) -> None:
            self.properties: dict[str, object] = {}
            self.styles: list[str] = []
            self.palettes: list[object] = []
            self.stylesheets: list[str] = []

        def property(self, name: str) -> object:
            return self.properties.get(name)

        def setProperty(self, name: str, value: object) -> None:  # noqa: N802
            self.properties[name] = value

        def setStyle(self, style: str) -> None:  # noqa: N802
            self.styles.append(style)

        def setPalette(self, palette: object) -> None:  # noqa: N802
            self.palettes.append(palette)

        def setStyleSheet(self, stylesheet: str) -> None:  # noqa: N802
            self.stylesheets.append(stylesheet)

    app = cast(QApplication, ThemeProbe())

    apply_theme(app)
    apply_theme(app)

    assert app.styles == ["Fusion"]
    assert len(app.palettes) == 1
    assert len(app.stylesheets) == 1


def test_theme_exposes_semantic_tokens_for_read_only_focus_and_feedback() -> None:
    css = stylesheet()

    assert {"sm", "md", "lg"} <= theme.SPACING.keys()
    assert {"body", "mono", "heading"} <= theme.TYPOGRAPHY.keys()
    assert {"text_read_only", "warning", "error", "border_focus"} <= COLORS.keys()
    assert 'QLabel[readOnly="true"]' in css
    assert "QPushButton:focus" in css
    assert "QLabel#cloudErrorLabel" in css
