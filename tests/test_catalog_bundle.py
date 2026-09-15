from __future__ import annotations

import json
from pathlib import Path

from test_xray_factions import _write_resource_tree

from editor.catalog import GameCatalog
from editor.catalog_bundle import load_catalog_payload
from editor.releases import release_by_id
from editor.xray_catalog import XRayCatalogProvider
from tools.build_web_catalogs import build_catalogs


def test_game_catalog_keeps_item_and_faction_release_ids_aligned(tmp_path: Path) -> None:
    _write_resource_tree(
        tmp_path,
        relation_dir="configs",
        faction_key="cop_only",
        display_name="CoP only",
    )

    bundle = XRayCatalogProvider().load_bundle(release_by_id("stalker-cop"), tmp_path)

    assert isinstance(bundle, GameCatalog)
    assert bundle.items.release_id == "stalker-cop"
    assert bundle.factions.release_id == "stalker-cop"


def test_browser_catalog_contains_the_same_release_scoped_factions(tmp_path: Path) -> None:
    _write_resource_tree(
        tmp_path,
        relation_dir="configs",
        faction_key="cop_only",
        display_name="CoP only",
    )

    payload = build_catalogs((("stalker-cop", tmp_path),))

    assert payload["schema_version"] == 1
    release = payload["releases"]["stalker-cop"]
    assert next(
        item for item in release["items"] if item["key"] == "ammo_fixture"
    )["display_name"] == "Ammo fixture"
    assert release["factions"] == [
        {
            "key": "actor",
            "display_name": None,
            "numeric_id": 0,
            "source": "gamedata/configs/creatures/game_relations.ltx#communities",
            "release_id": "stalker-cop",
        },
        {
            "key": "cop_only",
            "display_name": "CoP only",
            "numeric_id": 1,
            "source": "gamedata/configs/creatures/game_relations.ltx#communities",
            "release_id": "stalker-cop",
        },
    ]
    assert release["relation_addresses"] == [
        {"source": "actor", "target": "actor", "row": 0, "column": 0, "value": 0},
        {"source": "actor", "target": "cop_only", "row": 0, "column": 1, "value": 25},
        {"source": "cop_only", "target": "actor", "row": 1, "column": 0, "value": -25},
        {"source": "cop_only", "target": "cop_only", "row": 1, "column": 1, "value": 0},
    ]
    assert release["goodwill_min"] == -3000
    assert release["goodwill_max"] == 1000
    assert release["attitude_neutral_threshold"] == -999
    assert release["attitude_friend_threshold"] == 999

    encoded = json.dumps(payload, ensure_ascii=False)
    assert "save" not in encoded.casefold()
    assert str(tmp_path) not in encoded


def test_generated_catalog_loader_preserves_item_faction_and_upgrade_metadata() -> None:
    payload = {
        "schema_version": 1,
        "releases": {
            "stalker-cop": {
                "items": [
                    {
                        "key": "wpn_fixture",
                        "display_name": "Fixture rifle",
                        "category": "weapon",
                        "max_stack": None,
                        "serialization_family": "weapon_magazined",
                        "icon_x": 2,
                        "icon_y": 3,
                        "icon_texture": "ui_icon_equipment",
                    }
                ],
                "factions": [
                    {
                        "key": "actor",
                        "display_name": "Actor",
                        "numeric_id": 0,
                        "source": "fixture#communities",
                        "release_id": "stalker-cop",
                    },
                    {
                        "key": "stalker",
                        "display_name": "Stalker",
                        "numeric_id": 1,
                        "source": "fixture#communities",
                        "release_id": "stalker-cop",
                    },
                ],
                "relation_addresses": [
                    {"source": "actor", "target": "actor", "row": 0, "column": 0, "value": 0},
                    {"source": "actor", "target": "stalker", "row": 0, "column": 1, "value": 25},
                ],
                "upgrades": [
                    {
                        "key": "up_fixture",
                        "display_name": "Fixture upgrade",
                        "category": "weapon",
                        "item_key": "wpn_fixture",
                        "applicable_item_keys": ["wpn_fixture"],
                        "section": "up_sect_fixture",
                        "property": "prop_rpm",
                        "icon": "ui_upgrade_fixture",
                        "source": "fixture#up_fixture",
                        "release_id": "stalker-cop",
                    }
                ],
            }
        },
    }

    loaded = load_catalog_payload(json.dumps(payload, ensure_ascii=False))

    bundle = loaded["stalker-cop"]
    assert bundle.items.resolve("wpn_fixture").display_name == "Fixture rifle"  # type: ignore[union-attr]
    assert bundle.factions is not None
    assert bundle.factions.relation_address("actor", "stalker") == (0, 1)
    assert bundle.upgrades is not None
    assert bundle.upgrades.for_item("wpn_fixture")[0].key == "up_fixture"


def test_original_format_falls_back_to_checked_in_official_catalog() -> None:
    provider = XRayCatalogProvider()
    release = release_by_id("stalker-soc")

    bundle = provider.load_generated_bundle(release)

    assert bundle is not None
    assert bundle.items.resolve("medkit") is not None
    assert bundle.factions.resolve("actor").numeric_id == 0
    assert bundle.upgrades is not None
    assert bundle.upgrades.upgrades == ()
