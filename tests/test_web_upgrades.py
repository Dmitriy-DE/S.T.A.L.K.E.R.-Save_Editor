from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import web_bridge  # noqa: E402
from test_xray_upgrades import _upgrade_fixture  # noqa: E402


def _catalog_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "releases": {
            "stalker-cop": {
                "items": [
                    {
                        "key": "wpn_test",
                        "category": "weapon",
                        "serialization_family": "weapon",
                    }
                ],
                "factions": [],
                "upgrades": [
                    {
                        "key": "up_c_wpn_test",
                        "display_name": "Test upgrade",
                        "category": "weapon",
                        "item_key": "wpn_test",
                        "source": "fixture",
                    }
                ],
            }
        },
    }


@pytest.fixture(autouse=True)
def _restore_bridge_state():
    old = {
        "catalogs": dict(web_bridge._catalogs),
        "factions": dict(web_bridge._faction_catalogs),
        "upgrades": dict(web_bridge._upgrade_catalogs),
        "state": dict(web_bridge._state),
    }
    yield
    web_bridge._catalogs.clear()
    web_bridge._catalogs.update(old["catalogs"])
    web_bridge._faction_catalogs.clear()
    web_bridge._faction_catalogs.update(old["factions"])
    web_bridge._upgrade_catalogs.clear()
    web_bridge._upgrade_catalogs.update(old["upgrades"])
    web_bridge._state.clear()
    web_bridge._state.update(old["state"])


def test_web_bridge_exposes_and_prepares_equipment_upgrades() -> None:
    web_bridge.install_catalogs(json.dumps(_catalog_payload()))
    data = _upgrade_fixture()

    snapshot = json.loads(web_bridge.analyze(data, "slot.scop"))
    assert snapshot["capabilities"]["edit_upgrades"] is True
    assert snapshot["upgrade_catalog_available"] is True
    assert snapshot["catalog_upgrades"][0]["key"] == "up_c_wpn_test"
    assert snapshot["inventory"][0]["upgrades"] == [
        "up_a_wpn_test",
        "legacy_unknown",
    ]
    assert snapshot["inventory"][0]["upgrade_editable"] is True

    result = json.loads(
        web_bridge.prepare(
            None,
            "[]",
            "[]",
            "[]",
            "[]",
            "[]",
            "null",
            json.dumps([[0x3456, ["legacy_unknown", "up_c_wpn_test"]]]),
        )
    )

    assert result["upgrades"] == [
        [
            "0x00003456",
            ["up_a_wpn_test", "legacy_unknown"],
            ["legacy_unknown", "up_c_wpn_test"],
        ]
    ]


def test_web_bridge_rejects_upgrade_edit_without_release_capability() -> None:
    data = _upgrade_fixture()
    web_bridge.analyze(data, "slot.scop")
    web_bridge._state["format"] = type(
        "ReadOnlyFormat",
        (),
        {
            "release_id": "stalker-cop",
            "capabilities": type(
                "Capabilities",
                (),
                {"edit_upgrades": False},
            )(),
        },
    )()

    with pytest.raises(Exception, match="upgrades|read-only|evidence"):
        web_bridge.prepare(
            None,
            "[]",
            "[]",
            "[]",
            "[]",
            "[]",
            "null",
            json.dumps([[0x3456, []]]),
        )


def test_web_inventory_ui_has_catalog_bound_upgrade_controls() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert "upgradeDefinitionsFor" in script
    assert "upgrade_editable" in script
    assert "m_upgrades" in page
    assert "state.upgrades" in script
    assert "Исходный файл не изменяется" in page
