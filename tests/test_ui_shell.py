from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from ui.app_shell import AppShell
from ui.theme import stylesheet


def test_app_shell_exposes_canonical_global_navigation_and_footer(qtbot) -> None:
    shell = AppShell()
    qtbot.addWidget(shell)

    assert shell.destination_names == (
        "ЛОКАЛЬНЫЕ СОХРАНЕНИЯ",
        "STEAM CLOUD",
        "ИСТОРИЯ",
        "НАСТРОЙКИ",
    )
    assert [button.text() for button in shell.navigation_buttons] == list(
        shell.destination_names
    )
    assert shell.footer_hints.text() == ""

    with qtbot.waitSignal(shell.destination_requested, timeout=1_000) as signal:
        qtbot.mouseClick(shell.navigation_buttons[2], Qt.MouseButton.LeftButton)
    assert signal.args == ["history"]
    assert shell.active_destination == "history"


def test_reference_theme_is_real_shell_styling_without_old_xray_chrome() -> None:
    css = stylesheet()

    assert "#D6A62D" in css
    assert "QWidget#referenceShell" in css
    assert "QPushButton#globalNav" in css
    assert "border-image: url(\"" not in css
