from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QPushButton

from editor.service import EditorService
from ui.main_window import MainWindow
from ui.support_dialog import SupportDialog

ROOT = Path(__file__).parents[1]


def test_support_dialog_copies_each_payment_value_and_shows_feedback(qtbot) -> None:
    dialog = SupportDialog()
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Поддержать проект"
    assert "Адрес:" in "\n".join(
        label.text() for label in dialog.findChildren(QLabel, "supportDetail")
    )
    assert [field.text() for field in dialog.findChildren(QLineEdit, "supportValue")] == [
        "breygel.dima@gmail.com",
        "434350727",
        "TF5hpkAmF9vjbpaRpJ5ewpbCC122jED1ds",
    ]

    buttons = dialog.findChildren(QPushButton, "supportCopyButton")
    assert len(buttons) == 3
    for button, expected in zip(
        buttons,
        (
            "breygel.dima@gmail.com",
            "434350727",
            "TF5hpkAmF9vjbpaRpJ5ewpbCC122jED1ds",
        ),
        strict=True,
    ):
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert QApplication.clipboard().text() == expected
        assert button.text() == "Скопировано"


def test_main_window_opens_support_dialog_from_title_bar(qtbot) -> None:
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    assert window.app_shell.support_button.text() == "♡  ПОДДЕРЖАТЬ ПРОЕКТ"
    qtbot.mouseClick(window.app_shell.support_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: window._support_dialog is not None
        and window._support_dialog.isVisible()
    )

    dialog = window.findChild(QDialog, "supportDialog")
    assert dialog is not None
    assert dialog.isModal()
    dialog.close()


def test_web_support_shell_keeps_copyable_values_and_local_modal() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert 'id="support-button"' in html
    assert 'id="support-modal"' in html
    assert 'id="support-close"' in html
    assert "breygel.dima@gmail.com" in html
    assert "434350727" in html
    assert "TF5hpkAmF9vjbpaRpJ5ewpbCC122jED1ds" in html
    assert "Идентификатор Binance: 434350727" in html
    assert "Адрес:" in html
    assert "navigator.clipboard.writeText" in script
    assert 'button.textContent = t("Скопировано")' in script
    assert ".support-modal" in styles
