from __future__ import annotations

import json
from pathlib import Path

from test_xray_save import _fixture

from editor.platforms import user_data_dir
from tools import export_golden
from tools.export_golden import (
    default_output_path,
    export_roots,
    main,
    render_json,
)


def _write_fixture_set(root: Path, stalker2_save: bytes) -> dict[str, Path]:
    fixtures = {
        "stalker2": ("stalker2.sav", stalker2_save),
        "stalker-soc": ("soc.sav", _fixture(version=118, outer=3)),
        "stalker-cs": ("clear-sky.sav", _fixture(version=122, outer=5)),
        "stalker-cop": ("call-of-pripyat.scop", _fixture()),
    }
    paths: dict[str, Path] = {}
    for release, (filename, data) in fixtures.items():
        path = root / filename
        path.write_bytes(data)
        paths[release] = path
    return paths


def test_json_keys_are_sorted_and_floats_have_six_places() -> None:
    assert render_json({"z": 0.1, "a": 1.23456789}) == (
        '{\n  "a": 1.234568,\n  "z": 0.100000\n}\n'
    )


def test_synthetic_golden_export_matches_committed_vectors(
    tmp_path: Path,
    synthetic_save: bytes,
) -> None:
    root = tmp_path / "private-fixtures"
    root.mkdir()
    source_paths = _write_fixture_set(root, synthetic_save)
    original_bytes = {key: path.read_bytes() for key, path in source_paths.items()}

    payload = export_roots((root,))
    rendered = render_json(payload)
    golden = Path(__file__).parent / "golden" / "fixture-vectors.json"

    assert rendered == golden.read_text(encoding="utf-8")
    assert [sample["release"] for sample in payload["samples"]] == [
        "stalker-cop",
        "stalker-cs",
        "stalker-soc",
        "stalker2",
    ]
    assert {key: path.read_bytes() for key, path in source_paths.items()} == original_bytes
    assert str(root) not in rendered
    assert all(path.name not in rendered for path in source_paths.values())


def test_unrecognized_file_is_anonymized_in_the_export(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private-corpus"
    root.mkdir()
    (root / "private-slot.sav").write_bytes(b"not a supported save")

    payload = export_roots((root,))
    rendered = render_json(payload)
    sample = payload["samples"][0]

    assert sample["format"] == "unknown"
    assert sample["release"] == "unknown"
    assert sample["parse_status"] == "error"
    assert sample["error_type"]
    assert str(root) not in rendered
    assert "private-slot.sav" not in rendered


def test_unreadable_file_does_not_receive_a_fabricated_empty_file_hash(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "unreadable-corpus"
    root.mkdir()
    (root / "unreadable.sav").write_bytes(b"fixture")

    def fail_read(_path: Path):
        raise PermissionError("unreadable")

    monkeypatch.setattr(export_golden, "_read_snapshot", fail_read)
    sample = export_roots((root,))["samples"][0]

    assert sample["sha256"] is None
    assert sample["error_type"] == "PermissionError"


def test_mutation_vectors_capture_results_and_capability_gates(
    tmp_path: Path,
    synthetic_save: bytes,
) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    _write_fixture_set(root, synthetic_save)

    payload = export_roots((root,))
    samples = {sample["release"]: sample for sample in payload["samples"]}

    stalker2 = samples["stalker2"]
    assert stalker2["mutations"]["money_plus_one"]["result"] == "passed"
    # ED-3 (2026-09-26) opened S2 stack edits as experimental.
    assert stalker2["mutations"]["stack_delta"]["result"] == "passed"
    assert stalker2["state"]["capabilities"]["mutations"]["edit_stacks"][
        "maturity"
    ] == "experimental"
    assert stalker2["mutations"]["stack_delta"]["safety_checks"][
        "capability_allows"
    ] is True

    for release in ("stalker-soc", "stalker-cs", "stalker-cop"):
        assert samples[release]["mutations"]["money_plus_one"]["result"] == "passed"
        assert samples[release]["mutations"]["stack_delta"]["result"] == "passed"


def test_export_cli_defaults_to_the_local_rl5_corpus_directory(
    tmp_path: Path,
    synthetic_save: bytes,
    capsys,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _write_fixture_set(root, synthetic_save)
    output = tmp_path / "golden-vectors.json"

    assert default_output_path() == user_data_dir() / "corpus-lab" / "golden-vectors.json"
    assert main(["--roots", str(root), "--out", str(output)]) == 0
    stdout = capsys.readouterr().out
    exported = output.read_text(encoding="utf-8")

    assert "files=4" in stdout
    assert str(root) not in stdout + exported
    assert json.loads(exported)["schema_version"] == 1


def test_export_cli_rejects_a_repository_output_path(
    tmp_path: Path,
    synthetic_save: bytes,
    capsys,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    _write_fixture_set(root, synthetic_save)
    output = Path(__file__).parents[1] / ".private-corpus-vectors.json"

    assert main(["--roots", str(root), "--out", str(output)]) == 2
    assert "outside the repository" in capsys.readouterr().err
    assert not output.exists()
