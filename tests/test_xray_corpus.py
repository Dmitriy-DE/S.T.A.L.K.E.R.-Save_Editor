from __future__ import annotations

import json
from pathlib import Path

from test_xray_save import _fixture, _fixture_with_base_item

from editor.catalog import ItemCatalog, ItemDefinition
from editor.releases import official_releases
from editor.xray_save import COP_FORMAT
from tools.verify_xray_catalog import verify_catalog_sample
from tools.verify_xray_corpus import verify_corpus


def test_corpus_verifier_reports_aggregate_fixture_evidence_without_paths(
    tmp_path: Path,
) -> None:
    save = tmp_path / "private-name.scop"
    save.write_bytes(_fixture(128, 6))
    roots: dict[str, tuple[Path, ...]] = {
        release.id: () for release in official_releases()
    }
    roots["stalker-cop"] = (tmp_path,)

    result = verify_corpus(roots)
    cop = next(row for row in result["profiles"] if row["release_id"] == "stalker-cop")

    assert cop["candidate_count"] == 1
    assert cop["parsed_count"] == 1
    assert cop["sha_match_count"] == 1
    assert cop["edit_roundtrip_count"] >= 1
    rendered = json.dumps(result, ensure_ascii=False)
    assert "private-name.scop" not in rendered
    assert str(tmp_path) not in rendered


def test_catalog_verifier_round_trips_every_fixture_definition_in_memory() -> None:
    data = _fixture_with_base_item()
    catalog = ItemCatalog(
        "stalker-cop",
        None,
        (
            ItemDefinition(
                key="bandage_new",
                display_name="Bandage",
                category="item",
                unit_weight=0.1,
                width=1,
                height=1,
                max_stack=None,
                slots=(),
                prototype=None,
                source="fixture",
                serialization_family="base",
            ),
            ItemDefinition(
                key="bread_new",
                display_name="Bread",
                category="item",
                unit_weight=0.1,
                width=1,
                height=1,
                max_stack=None,
                slots=(),
                prototype=None,
                source="fixture",
                serialization_family="base",
            ),
        ),
    )

    result = verify_catalog_sample(data, COP_FORMAT, catalog)

    assert result["catalog_items"] == 2
    assert result["full_key_coverage_count"] == 2
    assert result["missing_serialization_families"] == {}
    assert result["roundtrip_added_count"] == 2
