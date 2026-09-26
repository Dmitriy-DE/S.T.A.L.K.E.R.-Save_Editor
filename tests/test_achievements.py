"""Steam achievements dialog (SC-3): list, and change only after a yes."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QMessageBox

from ui.achievements_dialog import AchievementsDialog


class _Fake:
    def __init__(self, state: dict[str, bool]) -> None:
        self.state = state
        self.changes: list[tuple[str, bool]] = []

    def list_achievements(self):
        return [
            {"api_name": key, "name": key.title(), "description": "d", "achieved": value, "unlock_time": 0, "hidden": False}
            for key, value in self.state.items()
        ]

    def set_achievement(self, api_name: str, achieved: bool):
        self.changes.append((api_name, achieved))
        self.state[api_name] = achieved

    def close(self):
        return None


def _dialog(qtbot, fake: _Fake) -> AchievementsDialog:
    dialog = AchievementsDialog(1, "Game", transport_factory=lambda _app: fake)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.table.rowCount() == len(fake.state) and dialog.table.isEnabled(), timeout=5000)
    return dialog


def test_lists_achievements_and_counts_unlocked(qtbot) -> None:
    dialog = _dialog(qtbot, _Fake({"first": True, "second": False}))
    assert "1" in dialog.status.text() and "2" in dialog.status.text()
    dialog.table.selectRow(1)
    assert dialog.unlock_button.isEnabled() and not dialog.clear_button.isEnabled()


def test_nothing_changes_without_confirmation(qtbot) -> None:
    fake = _Fake({"first": False})
    dialog = _dialog(qtbot, fake)
    dialog.table.selectRow(0)
    dialog.unlock_button.click()  # conftest answers "No"
    assert fake.changes == []


def test_confirmed_unlock_reaches_steam_and_refreshes(qtbot, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *_a, **_k: QMessageBox.StandardButton.Yes))
    fake = _Fake({"first": False})
    dialog = _dialog(qtbot, fake)
    dialog.table.selectRow(0)
    dialog.unlock_button.click()
    qtbot.waitUntil(lambda: fake.changes == [("first", True)] and dialog.table.isEnabled(), timeout=5000)
    qtbot.waitUntil(lambda: dialog.clear_button.isEnabled() or dialog.table.item(0, 2).text() != "", timeout=5000)
