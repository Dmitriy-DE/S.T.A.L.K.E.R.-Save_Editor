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


def test_reference_shell_exposes_canonical_navigation(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)

    assert window.app_shell.objectName() == "referenceShell"
    assert tuple(button.text() for button in window.app_shell.navigation_buttons) == (
        "ЛОКАЛЬНЫЕ СОХРАНЕНИЯ",
        "STEAM CLOUD",
        "ИСТОРИЯ",
        "НАСТРОЙКИ",
    )
    assert COLORS["bg_base"] in QApplication.instance().styleSheet()
    qtbot.mouseClick(window.app_shell.navigation_buttons[2], Qt.MouseButton.LeftButton)
    assert window.reference_stack.currentWidget() is window.history_reference_view


def test_reference_shell_metadata_tracks_real_snapshot(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    source = tmp_path / "локальный.sav"
    info = inspect_save(synthetic_save, with_inventory=True)
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    window._render_snapshot(LocalSnapshot(path=source, data=synthetic_save, info=info))

    assert source.name in window.editor_view.breadcrumb.text()
    assert "Локальный" in window.editor_view.source_label.text()
    assert "CRC PASS" in window.editor_view.integrity_label.text()
    assert "100" in window.editor_view.money_label.text()


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

        def setStyleSheet(self, value: str) -> None:  # noqa: N802
            self.stylesheets.append(value)

    app = cast(QApplication, ThemeProbe())
    apply_theme(app)
    apply_theme(app)
    assert app.styles == ["Fusion"]
    assert len(app.palettes) == 1
    assert len(app.stylesheets) == 1


def test_theme_exposes_semantic_tokens_and_packaged_font() -> None:
    css = stylesheet()
    assert {"sm", "md", "lg"} <= theme.SPACING.keys()
    assert {"body", "mono", "heading"} <= theme.TYPOGRAPHY.keys()
    assert {"text_read_only", "warning", "error", "border_focus"} <= COLORS.keys()
    assert 'QLabel[readOnly="true"]' in css
    assert "QPushButton:focus" in css
    assert "Liberation Sans Narrow" in css
