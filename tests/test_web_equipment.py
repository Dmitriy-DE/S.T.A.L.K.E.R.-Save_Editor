from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import web_bridge  # noqa: E402
from test_s2_equipment_inventory import WEAPON_HANDLE, _save_with_grid_weapon  # noqa: E402
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


def test_web_snapshot_exposes_s2_experimental_capability_but_keeps_unconfirmed_rows_read_only(
    synthetic_save: bytes,
) -> None:
    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))

    assert snapshot["capabilities"]["equipment"]["durability"]["maturity"] == "experimental"
    assert all(row["durability_editable"] is False for row in snapshot["equipment"])


def test_web_snapshot_exposes_s2_weapon_condition_and_read_only_modules(
    synthetic_save: bytes,
) -> None:
    snapshot = json.loads(
        web_bridge.analyze(_save_with_grid_weapon(synthetic_save), "weapon.sav")
    )

    inventory = next(row for row in snapshot["inventory"] if row["handle"] == WEAPON_HANDLE)
    equipment = next(row for row in snapshot["equipment"] if row["handle"] == WEAPON_HANDLE)
    assert inventory["condition"] == 0.75
    assert inventory["condition_editable"] is True
    assert inventory["modules"] == ["GunKharod_MagDefault", "HP_Laser_1"]
    assert equipment["category"] == "weapon"
    assert equipment["modules"] == ["GunKharod_MagDefault", "HP_Laser_1"]
    assert equipment["durability_editable"] is True
    assert equipment["observation_source"] == "grid"
    assert inventory["observation_source"] == "grid"


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


def test_web_equipment_is_merged_into_the_canonical_editor() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for marker in (
        'id="reference-inventory-filter"',
        'id="reference-equipment-summary"',
        'id="reference-item-fields"',
        'id="reference-inventory-table"',
        'data-upgrade-field="m_upgrades"',
    ):
        assert marker in html
    assert 'data-panel="equipment"' not in html
    for marker in (
        "function renderReferenceEditor",
        "function renderReferenceItemDetail",
        "condition_editable",
        "equipment_count",
        "reference-equipment-summary",
        "item.condition_editable",
        "state.durability",
    ):
        assert marker in app
