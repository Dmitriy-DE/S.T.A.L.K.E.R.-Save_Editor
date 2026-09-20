from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_xray_durability import _condition_fixture
from test_xray_save import _fixture

from editor.capabilities import gameplay_verified_release_ids
from editor.formats import by_id
from save_format import SaveError
from tools.prepare_ingame_verification import prepare_source_copy
from tools.verify_ingame_result import verify_resaved_save


def test_prepare_protocol_changes_only_money_and_keeps_source(tmp_path: Path) -> None:
    source = tmp_path / "source.scop"
    original = _fixture()
    source.write_bytes(original)

    manifest = prepare_source_copy(source, "stalker-cop", tmp_path / "run", 900)

    assert source.read_bytes() == original
    assert manifest.source_sha256 != manifest.edited_sha256
    assert manifest.original_money == 1234
    assert manifest.edited_money == 900
    payload = json.loads(manifest.manifest_path.read_text("utf-8"))
    assert "data" not in payload
    assert "save_bytes" not in payload


def test_verify_protocol_parses_the_resaved_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.scop"
    source.write_bytes(_fixture())
    manifest = prepare_source_copy(source, "stalker-cop", tmp_path / "run", 900)
    resaved = tmp_path / "resaved.scop"
    resaved.write_bytes(manifest.edited_path.read_bytes())

    result = verify_resaved_save(manifest.manifest_path, resaved)

    assert result.parser_ok is True
    assert result.money_matches is True
    assert result.observed_money == 900
    assert result.resaved_sha256 == manifest.edited_sha256


def test_prepare_and_verify_protocol_covers_equipment_durability(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.scop"
    source.write_bytes(
        _condition_fixture(version=128, outer=6, condition=0.25)
    )
    manifest = prepare_source_copy(
        source,
        "stalker-cop",
        tmp_path / "run",
        durability=((0x3456, 0.75),),
    )

    resaved = tmp_path / "resaved.scop"
    resaved.write_bytes(manifest.edited_path.read_bytes())
    result = verify_resaved_save(manifest.manifest_path, resaved)

    assert manifest.edited_money == manifest.original_money == 1234
    assert manifest.mutation == {
        "durability": [{"handle": 0x3456, "after": 0.75}]
    }
    assert result.parser_ok is True
    assert result.money_matches is True
    assert result.mutation_matches is True
    assert result.observed_mutation["durability"] == [
        {"handle": 0x3456, "after": pytest.approx(0.75)}
    ]


def test_verify_protocol_rejects_resaved_copy_with_wrong_equipment_value(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.scop"
    source.write_bytes(
        _condition_fixture(version=128, outer=6, condition=0.25)
    )
    manifest = prepare_source_copy(
        source,
        "stalker-cop",
        tmp_path / "run",
        durability=((0x3456, 0.75),),
    )
    wrong = prepare_source_copy(
        source,
        "stalker-cop",
        tmp_path / "wrong",
        durability=((0x3456, 0.5),),
    )

    result = verify_resaved_save(manifest.manifest_path, wrong.edited_path)

    assert result.parser_ok is True
    assert result.money_matches is True
    assert result.mutation_matches is False
    assert result.error and "durability" in result.error


def test_prepare_protocol_rejects_a_save_from_another_release(tmp_path: Path) -> None:
    source = tmp_path / "source.scop"
    source.write_bytes(_fixture())

    with pytest.raises(SaveError, match="не соответствует"):
        prepare_source_copy(source, "stalker-soc", tmp_path / "run", 900)


def test_prepare_protocol_rejects_combined_mutation_categories(tmp_path: Path) -> None:
    source = tmp_path / "source.scop"
    source.write_bytes(_condition_fixture(version=128, outer=6, condition=0.25))

    with pytest.raises(SaveError, match="одну категорию"):
        prepare_source_copy(
            source,
            "stalker-cop",
            tmp_path / "run",
            900,
            durability=((0x3456, 0.75),),
        )


def test_verify_protocol_reports_a_parser_failure_without_claiming_success(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.scop"
    source.write_bytes(_fixture())
    manifest = prepare_source_copy(source, "stalker-cop", tmp_path / "run", 900)
    resaved = tmp_path / "broken.scop"
    resaved.write_bytes(b"not a save")

    result = verify_resaved_save(manifest.manifest_path, resaved)

    assert result.parser_ok is False
    assert result.money_matches is False
    assert result.observed_money is None
    assert result.error


def test_owner_accepted_original_releases_are_gameplay_verified() -> None:
    assert gameplay_verified_release_ids() == frozenset(
        {"stalker-soc", "stalker-cs", "stalker-cop"}
    )
    assert by_id("stalker2").capabilities.edit_money is True
    assert by_id("stalker2").capabilities.is_experimental("edit_money") is True
    assert by_id("stalker-soc").capabilities.edit_money is True
    assert by_id("stalker-cs").capabilities.edit_money is True
    assert by_id("stalker-cop").capabilities.edit_money is True
