from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSpinBox

from editor.catalog import FactionCatalog, FactionDefinition
from save_format import SaveInfo
from ui.changes_view import ChangesView
from ui.faction_view import FactionView


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
        faction_relations=((0, 125), (1, -240)),
        faction_relations_editable=True,
    )


def test_faction_view_shows_values_and_respects_relation_gate(qtbot) -> None:
    view = FactionView()
    qtbot.addWidget(view)
    view.set_catalog(_catalog(), relation_enabled=False, reason="read-only")
    view.set_state(_info())

    assert view.relations_table.rowCount() == 2
    assert view.relations_table.item(0, 1).text() == "125"
    assert view.relations_table.item(1, 1).text() == "-240"
    assert not view.relations_table.cellWidget(0, 2).isEnabled()
    assert not view.relations_table.cellWidget(0, 3).isEnabled()


def test_faction_view_emits_staged_relation_and_changes_mark_risk(qtbot) -> None:
    view = FactionView()
    qtbot.addWidget(view)
    view.set_catalog(_catalog(), relation_enabled=True, reason="experimental")
    view.set_state(_info())

    spin = view.relations_table.cellWidget(1, 2)
    assert isinstance(spin, QSpinBox)
    spin.setValue(375)
    button = view.relations_table.cellWidget(1, 3)
    assert isinstance(button, QPushButton)
    with qtbot.waitSignal(view.relation_stage_requested, timeout=1_000) as signal:
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert signal.args == ["bandit", 375]

    changes = ChangesView()
    qtbot.addWidget(changes)
    changes.set_staged(
        _info(),
        None,
        {},
        staged_faction_relations={"bandit": 375},
        faction_catalog=_catalog(),
    )
    assert changes.changes_table.rowCount() == 1
    assert changes.changes_table.item(0, 4).text().startswith("С риском:")
