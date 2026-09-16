from __future__ import annotations

from pathlib import Path

import pytest

from editor.catalog import CatalogLookupError, GameCatalog
from editor.releases import release_by_id
from editor.xray_catalog import XRayCatalogProvider


def _write_resource_tree(
    root: Path,
    *,
    relation_dir: str,
    faction_key: str,
    display_name: str,
) -> None:
    config = root / "gamedata" / relation_dir
    text = config / "text" / "eng"
    text.mkdir(parents=True)
    (config / "creatures" / "game_relations.ltx").parent.mkdir(parents=True, exist_ok=True)
    (config / "creatures" / "game_relations.ltx").write_text(
        f"""
[game_relations]
communities = actor, 0, {faction_key}, 1
attitude_neutal_threshold = -999
attitude_friend_threshold = 999

[communities_relations]
actor = 0, 25
{faction_key} = -25, 0

[action_points]
community_goodwill_limits = -3000, 1000

[actor_communities]
actor = actor, actor
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (config / "items.ltx").write_text(
        """
[ammo_fixture]
class = AMMO
inv_name = st_ammo_fixture
box_size = 30
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (text / "string_table_general.xml").write_text(
        f"""<?xml version="1.0"?>
<string_table>
  <string id="{faction_key}"><text>{display_name}</text></string>
  <string id="st_ammo_fixture"><text>Ammo fixture</text></string>
</string_table>
""",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("release_id", "relation_dir", "faction_key", "display_name"),
    (
        ("stalker-soc", "config", "soc_faction", "Shadow faction"),
        ("stalker-cs", "configs", "cs_faction", "Clear Sky faction"),
        ("stalker-cop", "configs", "cop_faction", "Pripyat faction"),
    ),
)
def test_xray_faction_catalog_is_resource_derived_and_release_scoped(
    tmp_path: Path,
    release_id: str,
    relation_dir: str,
    faction_key: str,
    display_name: str,
) -> None:
    _write_resource_tree(
        tmp_path,
        relation_dir=relation_dir,
        faction_key=faction_key,
        display_name=display_name,
    )

    bundle = XRayCatalogProvider().load_bundle(release_by_id(release_id), tmp_path)

    assert isinstance(bundle, GameCatalog)
    assert bundle.release_id == release_id
    faction = bundle.factions.resolve(faction_key)
    assert faction.key == faction_key
    assert faction.display_name == display_name
    assert faction.release_id == release_id
    assert faction.numeric_id == 1
    assert bundle.factions.relation_address("actor", faction_key) == (0, 1)
    assert bundle.factions.default_relation("actor", faction_key) == 25
    assert bundle.factions.goodwill_min == -3000
    assert bundle.factions.goodwill_max == 1000
    assert bundle.factions.attitude_neutral_threshold == -999
    assert bundle.factions.attitude_friend_threshold == 999
    assert bundle.factions.resolve_numeric(1).key == faction_key


def test_faction_catalog_does_not_leak_keys_between_releases(tmp_path: Path) -> None:
    soc_root = tmp_path / "soc"
    cs_root = tmp_path / "cs"
    _write_resource_tree(
        soc_root,
        relation_dir="config",
        faction_key="only_soc",
        display_name="Only SoC",
    )
    _write_resource_tree(
        cs_root,
        relation_dir="configs",
        faction_key="only_cs",
        display_name="Only CS",
    )

    soc = XRayCatalogProvider().load_bundle(release_by_id("stalker-soc"), soc_root)
    cs = XRayCatalogProvider().load_bundle(release_by_id("stalker-cs"), cs_root)

    assert soc is not None and cs is not None
    assert soc.factions.resolve("only_soc").key == "only_soc"
    with pytest.raises(CatalogLookupError, match="stalker-soc"):
        soc.factions.resolve("only_cs")
    assert cs.factions.resolve("only_cs").key == "only_cs"
    with pytest.raises(CatalogLookupError, match="stalker-cs"):
        cs.factions.resolve("only_soc")


def test_missing_official_resources_return_no_bundle(tmp_path: Path) -> None:
    bundle = XRayCatalogProvider().load_bundle(release_by_id("stalker-cop"), tmp_path / "missing")

    assert bundle is None
