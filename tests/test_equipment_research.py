from __future__ import annotations

import hashlib
import json

import pytest

from editor.equipment import equipment_support_for_release
from editor.equipment_research import analyze_equipment_samples
from editor.releases import official_releases
from tools.research_equipment import main


def test_research_report_records_hashes_observations_and_s2_blockers(
    tmp_path, synthetic_save: bytes
) -> None:
    first = tmp_path / "one.sav"
    second = tmp_path / "two.sav"
    first.write_bytes(synthetic_save)
    second.write_bytes(synthetic_save)
    before = first.read_bytes()

    report = analyze_equipment_samples((first, second), expected_release_id="stalker2")
    payload = report.as_dict()

    assert report.release_id == "stalker2"
    assert report.maturity == "experimental"
    assert len(report.samples) == 2
    assert report.samples[0].sha256 == hashlib.sha256(synthetic_save).hexdigest()
    assert report.samples[0].category_counts
    assert any("three" in blocker.lower() for blocker in report.blockers)
    assert any("load/re-save" in blocker for blocker in report.blockers)
    assert payload["samples"][0]["path"] == str(first)
    assert first.read_bytes() == before


def test_research_rejects_mixed_release_samples(tmp_path, synthetic_save: bytes) -> None:
    path = tmp_path / "sample.sav"
    path.write_bytes(synthetic_save)

    with pytest.raises(ValueError, match="expected release"):
        analyze_equipment_samples((path,), expected_release_id="stalker-cop")


def test_every_official_profile_has_explicit_equipment_maturity() -> None:
    profiles = {release.id for release in official_releases()}

    assert len(profiles) == 7
    for release_id in profiles:
        support = equipment_support_for_release(release_id)
        assert set(support.as_dict()) == {
            "durability",
            "upgrades",
            "placement",
            "add",
            "remove",
        }
        assert all(feature["maturity"] for feature in support.as_dict().values())


def test_research_report_is_json_serializable(tmp_path, synthetic_save: bytes) -> None:
    path = tmp_path / "sample.sav"
    path.write_bytes(synthetic_save)

    report = analyze_equipment_samples((path,))

    assert json.loads(json.dumps(report.as_dict(), ensure_ascii=False))["release_id"] == "stalker2"


def test_research_cli_emits_json_without_writing_the_sample(
    tmp_path, synthetic_save: bytes, capsys
) -> None:
    path = tmp_path / "sample.sav"
    path.write_bytes(synthetic_save)

    assert main(["--json", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["release_id"] == "stalker2"
    assert output["samples"][0]["sha256"] == hashlib.sha256(synthetic_save).hexdigest()
