from __future__ import annotations

import hashlib
import json
import struct

import pytest

import editor.equipment_research as equipment_research
import save_format as sf
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
            "categories",
            "device_subtypes",
            "icon_source",
        }
        serialized = support.as_dict()
        feature_values = [
            serialized[name]
            for name in ("durability", "upgrades", "placement", "add", "remove")
        ]
        assert all(
            isinstance(feature, dict) and feature.get("maturity")
            for feature in feature_values
        )


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

    assert main(["--sample", str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["release_id"] == "stalker2"


def test_corpus_report_anonymizes_sources_and_records_required_totals(
    tmp_path, synthetic_save: bytes
) -> None:
    root = tmp_path / "private-saves"
    root.mkdir()
    (root / "slot-a.sav").write_bytes(synthetic_save)
    (root / "not-a-save.bin").write_bytes(b"not a save")

    report = equipment_research.analyze_equipment_corpus(root)
    payload = report.as_dict()

    assert payload["file_count"] == 2
    assert payload["accepted_count"] == 1
    assert payload["rejected_count"] == 1
    assert payload["samples"][0]["sample_id"] == "sample-001"
    assert payload["samples"][0]["packed_size"] == len(synthetic_save)
    assert payload["samples"][0]["raw_size"] == len(sf.decompress_save(synthetic_save))
    assert payload["samples"][0]["actor_owned_count"] == 4
    assert payload["samples"][0]["grid_count"] == 2
    assert payload["samples"][0]["equipped_count"] == 0
    assert "condition_anchor_status" in payload
    assert "category_totals" in payload
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(root) not in serialized
    assert synthetic_save.hex() not in serialized


def test_corpus_rejects_an_input_changed_during_analysis(
    tmp_path, synthetic_save: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "slot.sav"
    path.write_bytes(synthetic_save)
    original = equipment_research.equipment_items

    def mutate_after_parse(*args, **kwargs):
        path.write_bytes(synthetic_save + b"changed")
        return original(*args, **kwargs)

    monkeypatch.setattr(equipment_research, "equipment_items", mutate_after_parse)

    with pytest.raises(ValueError, match="changed during analysis"):
        equipment_research.analyze_equipment_corpus(tmp_path)


def test_corpus_cli_accepts_an_explicit_root_and_output_path(
    tmp_path, synthetic_save: bytes, capsys
) -> None:
    root = tmp_path / "input"
    root.mkdir()
    source = root / "slot.sav"
    source.write_bytes(synthetic_save)
    output = tmp_path / "report.json"
    before = (source.read_bytes(), source.stat().st_size, source.stat().st_mtime_ns)

    assert main(["--input-root", str(root), "--output", str(output), "--json"]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["accepted_count"] == 1
    assert str(root) not in output.read_text(encoding="utf-8")
    assert (source.read_bytes(), source.stat().st_size, source.stat().st_mtime_ns) == before
    assert json.loads(capsys.readouterr().out)["file_count"] == 1


def test_name_table_only_nvg_and_binocular_names_do_not_create_owned_rows(
    tmp_path, synthetic_save: bytes
) -> None:
    raw = bytearray(sf.decompress_save(synthetic_save))
    names = ("Binoculars_02", "NVG_Gen2")
    raw += struct.pack("<H", len(names))
    for name in names:
        encoded = name.encode("utf-8")
        raw += struct.pack("<H", len(encoded)) + encoded
    path = tmp_path / "metadata-only.sav"
    path.write_bytes(sf.rebuild_uncompressed(bytes(raw)))

    report = equipment_research.analyze_equipment_corpus(tmp_path)
    sample = report.as_dict()["samples"][0]

    assert sample["actor_owned_count"] == 4
    assert sample["grid_count"] == 2
    assert sample["equipped_count"] == 0
    assert sample["category_counts"].get("device", 0) == 0
