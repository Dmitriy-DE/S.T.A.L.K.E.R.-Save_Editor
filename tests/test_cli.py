"""Regression tests for the command line entry point.

The CLI is the interface used for research and scripted edits, and it had no
coverage: every safe-write guarantee was only tested through the service layer.
These tests drive `cli.main` directly with synthetic bytes - no private save, no
Steam, no network.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from test_xray_save import _fixture

import cli
import save_format as sf
from editor.xray_save import COP_FORMAT, inspect_xray


def _write_save(tmp_path: Path, data: bytes, name: str = "slot.sav") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_info_reports_money_and_leaves_the_file_untouched(
    tmp_path: Path, synthetic_save: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_save(tmp_path, synthetic_save)
    before = path.read_bytes()

    assert cli.main(["info", str(path)]) == 0

    assert "Money: 100" in capsys.readouterr().out
    assert path.read_bytes() == before


def test_set_money_writes_a_new_file_and_keeps_the_source(
    tmp_path: Path, synthetic_save: bytes
) -> None:
    path = _write_save(tmp_path, synthetic_save)
    source_sha = hashlib.sha256(synthetic_save).hexdigest()
    output = tmp_path / "edited.sav"

    assert cli.main(
        [
            "set-money",
            str(path),
            "900000",
            "-o",
            str(output),
            "--backup-dir",
            str(tmp_path / "backups"),
        ]
    ) == 0

    assert hashlib.sha256(path.read_bytes()).hexdigest() == source_sha
    assert sf.inspect_save(output.read_bytes()).money == 900000


def test_set_money_refuses_to_overwrite_the_source(
    tmp_path: Path, synthetic_save: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_save(tmp_path, synthetic_save)

    exit_code = cli.main(
        ["set-money", str(path), "1", "-o", str(path), "--backup-dir", str(tmp_path / "b")]
    )

    assert exit_code == 2
    assert "Error:" in capsys.readouterr().err
    assert sf.inspect_save(path.read_bytes()).money == 100


def test_corrupt_input_fails_closed(
    tmp_path: Path, synthetic_save: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = bytearray(synthetic_save)
    broken[-1] ^= 0xFF
    path = _write_save(tmp_path, bytes(broken))

    exit_code = cli.main(
        ["set-money", str(path), "5", "-o", str(tmp_path / "out.sav"), "--backup-dir", str(tmp_path)]
    )

    assert exit_code == 2
    assert "Error:" in capsys.readouterr().err
    assert not (tmp_path / "out.sav").exists()


def test_edit_without_changes_is_rejected(
    tmp_path: Path, synthetic_save: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_save(tmp_path, synthetic_save)

    assert cli.main(["edit", str(path), "--backup-dir", str(tmp_path / "b")]) == 2
    assert "Нет изменений" in capsys.readouterr().err


def test_unknown_command_exits_with_argparse_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["definitely-not-a-command"])
    assert excinfo.value.code == 2


def test_build_parser_has_no_side_effects() -> None:
    first = cli.build_parser()
    second = cli.build_parser()
    assert first is not second
    assert {action.dest for action in first._actions} == {
        action.dest for action in second._actions
    }


def test_missing_file_reports_an_error_instead_of_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["info", str(tmp_path / "absent.sav")])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


def test_xray_info_and_stack_edit_use_the_shared_cli_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = _fixture()
    path = _write_save(tmp_path, data, "slot.scop")
    output = tmp_path / "edited.scop"

    assert cli.main(["info", str(path)]) == 0
    info_output = capsys.readouterr().out
    assert "Format: stalker-cop" in info_output
    assert "Integrity: X-Ray LZO/container OK" in info_output

    item = inspect_xray(data, COP_FORMAT).inventory[0]
    assert cli.main(
        [
            "set-stack",
            str(path),
            hex(item.handle),
            "44",
            "-o",
            str(output),
            "--backup-dir",
            str(tmp_path / "backups"),
        ]
    ) == 0
    capsys.readouterr()
    assert path.read_bytes() == data
    assert inspect_xray(output.read_bytes(), COP_FORMAT).inventory[0].count == 44
