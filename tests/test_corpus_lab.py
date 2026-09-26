from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from test_xray_save import _fixture

from editor.xray_container import XRayContainer
from tools import corpus_lab
from tools.corpus_lab import analyze_roots, main


def test_corpus_report_is_path_free_and_tests_only_in_memory_copies(
    tmp_path: Path,
    synthetic_save: bytes,
    capsys,
) -> None:
    root = tmp_path / "private-saves"
    root.mkdir()
    source = root / "my-private-slot.sav"
    source.write_bytes(synthetic_save)
    before = (source.read_bytes(), source.stat().st_size, source.stat().st_mtime_ns)

    report = analyze_roots((root,))
    payload = report.as_dict()
    sample = payload["samples"][0]
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["files_seen"] == 1
    assert payload["parsed_count"] == 1
    assert sample["sha256"] == hashlib.sha256(synthetic_save).hexdigest()
    assert sample["release"] == "stalker2"
    assert sample["parse_status"] == "ok"
    assert sample["item_count"] == 2
    assert sample["name_coverage"]["total"] == 2
    assert 0 <= sample["name_coverage"]["covered"] <= 2
    assert sample["icon_coverage"]["total"] == 2
    assert 0 <= sample["icon_coverage"]["covered"] <= 2
    assert "edit_money" in sample["available_operations"]
    assert sample["operation_levels"]["edit_money"] == "experimental"
    assert sample["operation_levels"]["edit_stacks"] == "experimental"
    assert sample["no_op_round_trip"] == "passed"
    assert sample["test_mutations"]["money_plus_one"]["status"] == "passed"
    assert sample["test_mutations"]["stack_delta"]["status"] == "passed"
    assert sample["modded"] is True
    assert str(root) not in serialized
    assert source.name not in serialized
    assert (source.read_bytes(), source.stat().st_size, source.stat().st_mtime_ns) == before

    out = tmp_path / "reports"
    assert main(["--roots", str(root), "--out", str(out)]) == 0
    stdout = capsys.readouterr().out
    markdown = (out / "report.md").read_text(encoding="utf-8")
    json_report = (out / "report.json").read_text(encoding="utf-8")
    assert "files=1" in stdout
    assert str(root) not in markdown + json_report
    assert source.name not in markdown + json_report


def test_corpus_report_counts_parse_errors_without_paths(
    tmp_path: Path,
    synthetic_save: bytes,
) -> None:
    root = tmp_path / "inputs"
    root.mkdir()
    (root / "valid.sav").write_bytes(synthetic_save)
    (root / "invalid-private-name.sav").write_bytes(b"not a save")
    (root / "not-a-save.txt").write_text("ignored", encoding="utf-8")

    payload = analyze_roots((root,)).as_dict()
    serialized = json.dumps(payload, ensure_ascii=False)
    rejected = next(sample for sample in payload["samples"] if sample["parse_status"] == "error")

    assert payload["files_seen"] == 2
    assert payload["parsed_count"] == 1
    assert payload["parse_error_count"] == 1
    assert rejected["release"] == "unknown"
    assert rejected["error_type"]
    assert str(root) not in serialized
    assert "invalid-private-name.sav" not in serialized


def test_catalog_failure_does_not_turn_a_parsed_save_into_a_parse_error(
    tmp_path: Path,
    synthetic_save: bytes,
    monkeypatch,
) -> None:
    root = tmp_path / "catalog-failure-corpus"
    root.mkdir()
    (root / "slot.sav").write_bytes(synthetic_save)

    def fail_catalog_load(_format, _path):
        raise OSError("catalog unavailable")

    monkeypatch.setattr(corpus_lab, "_catalogs_for", fail_catalog_load)
    sample = analyze_roots((root,)).as_dict()["samples"][0]

    assert sample["parse_status"] == "ok"
    assert sample["release"] == "stalker2"
    assert sample["no_op_round_trip"] == "passed"


def test_money_plus_one_is_skipped_at_the_existing_writer_limit(
    synthetic_save: bytes,
) -> None:
    format_ = corpus_lab.detect_or_raise(synthetic_save, display_name="synthetic")

    result = corpus_lab._test_money_copy(format_, synthetic_save, 2_000_000_000)

    assert result.status == "skipped"


def test_corpus_lab_round_trips_and_mutates_only_an_xray_copy(tmp_path: Path) -> None:
    root = tmp_path / "xray-corpus"
    root.mkdir()
    source = root / "xray-slot.sav"
    source.write_bytes(_fixture())
    before = source.read_bytes()

    sample = analyze_roots((root,)).as_dict()["samples"][0]

    assert sample["release"] == "stalker-cop"
    assert sample["format"] == "stalker-cop"
    assert sample["parse_status"] == "ok"
    assert sample["no_op_round_trip"] == "passed"
    assert sample["test_mutations"]["money_plus_one"]["status"] == "passed"
    assert sample["test_mutations"]["stack_delta"]["status"] == "passed"
    assert sample["test_mutations"]["stack_delta"]["delta"] == 1
    assert sample["modded"] is False
    assert source.read_bytes() == before


def test_corpus_lab_marks_unknown_xray_chunks_as_modded(tmp_path: Path) -> None:
    root = tmp_path / "unknown-section-corpus"
    root.mkdir()
    source = root / "save.sav"
    container = XRayContainer.from_bytes(_fixture())
    unknown = b"foreign-section"
    raw = container.raw + struct.pack("<II", 77, len(unknown)) + unknown
    source.write_bytes(container.build(raw))

    sample = analyze_roots((root,)).as_dict()["samples"][0]

    assert sample["parse_status"] == "ok"
    assert sample["modded"] is True
    assert sample["modded_reasons"] == ["unknown_sections"]


def test_corpus_lab_marks_a_foreign_catalog_as_modded(tmp_path: Path) -> None:
    root = tmp_path / "foreign-catalog-corpus"
    save_directory = root / "gamedata" / "config" / "ogsm"
    save_directory.mkdir(parents=True)
    (save_directory / "save.sav").write_bytes(_fixture())

    sample = analyze_roots((root,)).as_dict()["samples"][0]

    assert sample["parse_status"] == "ok"
    assert sample["modded"] is True
    assert "foreign_catalog" in sample["modded_reasons"]


def test_corpus_cli_rejects_output_inside_an_input_root(
    tmp_path: Path,
    synthetic_save: bytes,
    capsys,
) -> None:
    root = tmp_path / "input"
    root.mkdir()
    (root / "slot.sav").write_bytes(synthetic_save)

    assert main(["--roots", str(root), "--out", str(root / "corpus-lab")]) == 2
    assert "overlap" in capsys.readouterr().err.casefold()
    assert not (root / "corpus-lab").exists()
