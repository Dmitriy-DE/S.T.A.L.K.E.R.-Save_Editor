from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import web_bridge  # noqa: E402
from test_xray_durability import _condition_fixture  # noqa: E402


def test_web_snapshot_exposes_shared_equipment_projection() -> None:
    snapshot = json.loads(
        web_bridge.analyze(
            _condition_fixture(version=128, outer=6, name="helm_battle"),
            "helmet.scop",
        )
    )

    assert snapshot["equipment_count"] == 1
    row = snapshot["equipment"][0]
    assert row["category"] == "helmet"
    assert row["serializer_family"] == "outfit"
    assert row["location"] == "unknown"
    assert row["durability"]["maturity"] == "experimental"
    assert row["durability_editable"] is True
    assert snapshot["capabilities"]["equipment"]["durability"]["maturity"] == "experimental"


def test_web_snapshot_keeps_s2_equipment_read_only_until_evidence(
    synthetic_save: bytes,
) -> None:
    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))

    assert snapshot["capabilities"]["equipment"]["durability"]["maturity"] == "research"
    assert all(row["durability_editable"] is False for row in snapshot["equipment"])


def test_web_snapshot_does_not_expose_soc_helmet_category() -> None:
    snapshot = json.loads(
        web_bridge.analyze(
            _condition_fixture(version=118, outer=3, name="helm_battle"),
            "helmet.sav",
        )
    )

    assert snapshot["release_id"] == "stalker-soc"
    assert snapshot["helmet_category_supported"] is False
    assert snapshot["equipment"][0]["category"] == "armor"


def test_web_equipment_panel_contains_filters_and_bulk_repair_controls() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for marker in (
        'data-panel="equipment"',
        'id="equipment-search"',
        'id="equipment-filter"',
        'id="equipment"',
        'id="equipment-percent"',
        'id="equipment-repair-selected"',
        'id="equipment-repair-full"',
        'id="equipment-repair-damaged"',
        'id="equipment-repair-equipped"',
    ):
        assert marker in html
    for marker in (
        "function renderEquipment",
        "stageEquipmentRepair",
        'el("equipment-repair-damaged")',
        'el("equipment-filter")',
        'helmet_category_supported',
    ):
        assert marker in app
