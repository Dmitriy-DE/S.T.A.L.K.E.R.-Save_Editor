from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from editor.catalog import FactionCatalog, FactionDefinition
from save_format import SaveInfo
from ui.faction_view import FactionView


def _catalog() -> FactionCatalog:
    return FactionCatalog(
        release_id="stalker-cop",
        source_root=None,
        factions=(
            FactionDefinition("actor", "Actor", "fixture", "stalker-cop", 0),
            FactionDefinition("bandit", "Bandit", "fixture", "stalker-cop", 1),
        ),
    )


def _info(*, editable: bool = False) -> SaveInfo:
    return SaveInfo(
        packed_size=1,
        unpacked_size=1,
        stored_crc32=0,
        computed_crc32=0,
        crc_ok=True,
        sha256="0" * 64,
        money=None,
        money_anchor_count=0,
        player_faction_index=0,
        player_faction_editable=editable,
    )


def test_player_faction_view_shows_snapshot_and_read_only_gate(qtbot) -> None:
    view = FactionView()
    qtbot.addWidget(view)
    view.set_catalog(_catalog(), relation_enabled=False, player_enabled=False, reason="read-only")
    view.set_state(_info())

    assert view.player_faction_combo.count() == 2
    assert view.player_faction_current.text() == "Actor · actor"
    assert not view.player_faction_combo.isEnabled()
    assert not view.player_faction_stage_button.isEnabled()


def test_player_faction_view_emits_staged_key(qtbot) -> None:
    view = FactionView()
    qtbot.addWidget(view)
    view.set_catalog(_catalog(), relation_enabled=False, player_enabled=True, reason="experimental")
    view.set_state(_info(editable=True))
    view.player_faction_combo.setCurrentIndex(1)

    with qtbot.waitSignal(view.player_faction_stage_requested, timeout=1_000) as signal:
        button = view.player_faction_stage_button
        assert isinstance(button, QPushButton)
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert signal.args == ["bandit"]
