from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSpinBox

from editor.catalog import FactionCatalog, FactionDefinition
from save_format import SaveInfo
from ui.changes_view import ChangesView
from ui.faction_view import FactionView

ROOT = Path(__file__).resolve().parents[1]


def _catalog() -> FactionCatalog:
    return FactionCatalog(
        release_id="stalker-cop",
        source_root=None,
        factions=(
            FactionDefinition("actor", "Actor", "fixture", "stalker-cop", 0),
            FactionDefinition("bandit", "Bandit", "fixture", "stalker-cop", 1),
        ),
        goodwill_min=-3000,
        goodwill_max=1000,
    )


def _info() -> SaveInfo:
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
        faction_relations=((0, 125), (1, -240)),
    )


def test_faction_view_shows_snapshot_values_and_respects_read_only_gate(qtbot) -> None:
    view = FactionView()
    qtbot.addWidget(view)

    view.set_catalog(
        _catalog(),
        relation_enabled=False,
        player_enabled=False,
        reason="read-only до игрового evidence",
    )
    view.set_state(_info())

    assert view.player_faction_combo.count() == 2
    assert "actor" in view.player_faction_current.text().lower()
    assert view.relations_table.rowCount() == 2
    assert view.relations_table.item(0, 1).text() == "125"
    assert view.relations_table.item(1, 1).text() == "-240"
    assert not view.player_faction_combo.isEnabled()
    assert not view.player_faction_stage_button.isEnabled()
    assert not view.relations_table.cellWidget(0, 2).isEnabled()
    assert not view.relations_table.cellWidget(0, 3).isEnabled()


def test_faction_view_emits_staged_relation_and_player_selection(qtbot) -> None:
    view = FactionView()
    qtbot.addWidget(view)
    view.set_catalog(
        _catalog(),
        relation_enabled=True,
        player_enabled=True,
        reason="Экспериментально: backup обязателен",
    )
    view.set_state(_info())
    assert "Экспериментально" in view.status_label.text()

    goodwill = view.relations_table.cellWidget(1, 2)
    assert isinstance(goodwill, QSpinBox)
    goodwill.setValue(375)
    relation_button = view.relations_table.cellWidget(1, 3)
    assert isinstance(relation_button, QPushButton)
    with qtbot.waitSignal(view.relation_stage_requested, timeout=1_000) as relation:
        qtbot.mouseClick(relation_button, Qt.MouseButton.LeftButton)
    assert relation.args == ["bandit", 375]

    view.player_faction_combo.setCurrentIndex(1)
    with qtbot.waitSignal(view.player_faction_stage_requested, timeout=1_000) as player:
        qtbot.mouseClick(view.player_faction_stage_button, Qt.MouseButton.LeftButton)
    assert player.args == ["bandit"]


def test_web_faction_controls_use_the_shared_bridge_and_zone_styles() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert 'id="faction-relations"' in html
    assert 'id="player-faction-select"' in html
    assert 'id="player-faction-stage"' in html
    assert "state.factionRelations" in script
    assert "state.playerFaction" in script
    assert "relations," in script
    assert "experimental_fields" in script
    assert "Экспериментально" in script
    assert "ОПАСНО" in script
    assert "С риском" in script
    assert "compact-grid" in styles
    assert "faction-warning" in styles


def test_changes_view_marks_behavior_and_inventory_risks(qtbot) -> None:
    view = ChangesView()
    qtbot.addWidget(view)

    view.set_staged(
        _info(),
        None,
        {},
        staged_adds={"ammo_9x39": 1},
        staged_detach={0x1234: True},
        staged_faction_relations={"bandit": 375},
        staged_player_faction="bandit",
        faction_catalog=_catalog(),
        experimental_fields={
            "add_items",
            "remove_items",
            "edit_relations",
            "edit_player_faction",
        },
    )

    support = [
        view.changes_table.item(row, 4).text()
        for row in range(view.changes_table.rowCount())
    ]
    assert any(text.startswith("ОПАСНО:") for text in support[:2])
    assert any(text.startswith("С риском:") for text in support)
    assert sum(text.startswith("ОПАСНО:") for text in support) == 3
