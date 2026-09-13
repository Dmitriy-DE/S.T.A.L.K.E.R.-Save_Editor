from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import editor.storage as storage
from editor.models import EditPlan, SourceRef
from editor.prepare import prepare_edit
from save_format import SaveError


def _prepared(tmp_path: Path, data: bytes):
    source = tmp_path / "source.sav"
    source.write_bytes(data)
    plan = EditPlan(
        source=SourceRef(
            kind="local",
            locator=str(source),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        money=900,
    )
    return source, prepare_edit(data, plan)


def _write_journal(
    journal: Path,
    *,
    backup_path: Path,
    backup_sha256: str,
    status: str = "verified",
    created_at: str = "2026-09-13T18:00:00+00:00",
) -> None:
    journal.write_text(
        json.dumps(
            {
                "version": 1,
                "status": status,
                "created_at": created_at,
                "source_path": "/saves/original.sav",
                "source_sha256": backup_sha256,
                "output_path": "/saves/edited.sav",
                "output_sha256": backup_sha256,
                "backup_path": str(backup_path),
                "operation": {"money": 900, "stack_count": 0},
            }
        ),
        encoding="utf-8",
    )


def test_list_backups_distinguishes_verified_missing_and_corrupt(
    tmp_path: Path, synthetic_save: bytes
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    expected_sha = hashlib.sha256(synthetic_save).hexdigest()

    valid_backup = backup_dir / "valid_ORIGINAL.sav"
    valid_backup.write_bytes(synthetic_save)
    _write_journal(
        valid_backup.with_suffix(".json"),
        backup_path=valid_backup,
        backup_sha256=expected_sha,
    )

    missing_backup = backup_dir / "missing_ORIGINAL.sav"
    _write_journal(
        missing_backup.with_suffix(".json"),
        backup_path=missing_backup,
        backup_sha256=expected_sha,
    )

    corrupt_backup = backup_dir / "corrupt_ORIGINAL.sav"
    corrupt_backup.write_bytes(b"wrong bytes")
    _write_journal(
        corrupt_backup.with_suffix(".json"),
        backup_path=corrupt_backup,
        backup_sha256=expected_sha,
    )

    malformed = backup_dir / "malformed.json"
    malformed.write_text("{broken", encoding="utf-8")

    records = storage.list_backups((backup_dir,))
    by_name = {record.journal_path.name: record for record in records}

    assert by_name["valid_ORIGINAL.json"].status == "verified"
    assert by_name["missing_ORIGINAL.json"].status == "missing"
    assert by_name["corrupt_ORIGINAL.json"].status == "corrupt"
    assert by_name["malformed.json"].status == "corrupt"
    assert by_name["valid_ORIGINAL.json"].source_path == "/saves/original.sav"
    assert by_name["valid_ORIGINAL.json"].operation["money"] == 900


def test_restore_backup_is_byte_exact_and_does_not_change_backup(
    tmp_path: Path, synthetic_save: bytes
) -> None:
    source, prepared = _prepared(tmp_path, synthetic_save)
    output = tmp_path / "edited.sav"
    backup_dir = tmp_path / "backups"
    receipt = storage.export_local(source, output, prepared, backup_dir)
    journal = receipt.backup_path.with_suffix(".json")
    restored = tmp_path / "restored.sav"

    restore_receipt = storage.restore_backup(journal, restored)

    assert restore_receipt.output_path == restored
    assert restore_receipt.backup_path == receipt.backup_path
    assert restore_receipt.output_sha256 == hashlib.sha256(synthetic_save).hexdigest()
    assert restored.read_bytes() == synthetic_save
    assert receipt.backup_path.read_bytes() == synthetic_save
    assert output.read_bytes() == prepared.data


@pytest.mark.parametrize("kind", ["missing", "corrupt"])
def test_restore_backup_rejects_unusable_record_without_output(
    tmp_path: Path, synthetic_save: bytes, kind: str
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = backup_dir / f"{kind}_ORIGINAL.sav"
    if kind == "corrupt":
        backup.write_bytes(b"not the expected save")
    journal = backup.with_suffix(".json")
    _write_journal(
        journal,
        backup_path=backup,
        backup_sha256=hashlib.sha256(synthetic_save).hexdigest(),
    )
    destination = tmp_path / "restored.sav"

    with pytest.raises(SaveError, match="missing|отсутств|corrupt|повреж"):
        storage.restore_backup(journal, destination)

    assert not destination.exists()


def test_restore_backup_refuses_existing_destination_and_preserves_previous(
    tmp_path: Path, synthetic_save: bytes
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = backup_dir / "valid_ORIGINAL.sav"
    backup.write_bytes(synthetic_save)
    journal = backup.with_suffix(".json")
    _write_journal(
        journal,
        backup_path=backup,
        backup_sha256=hashlib.sha256(synthetic_save).hexdigest(),
    )
    destination = tmp_path / "existing.sav"
    previous = b"keep this file"
    destination.write_bytes(previous)

    with pytest.raises(SaveError, match="exist|существ"):
        storage.restore_backup(journal, destination)

    assert destination.read_bytes() == previous
    assert backup.read_bytes() == synthetic_save


def test_restore_backup_partial_publish_failure_cleans_temp_and_keeps_backup(
    tmp_path: Path, synthetic_save: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = backup_dir / "valid_ORIGINAL.sav"
    backup.write_bytes(synthetic_save)
    journal = backup.with_suffix(".json")
    _write_journal(
        journal,
        backup_path=backup,
        backup_sha256=hashlib.sha256(synthetic_save).hexdigest(),
    )
    destination = tmp_path / "restored.sav"

    def fail_publish(temp_path: Path, destination_path: Path) -> None:
        raise SaveError("injected restore publish failure")

    monkeypatch.setattr(storage, "_publish_noreplace", fail_publish)
    with pytest.raises(SaveError, match="publish"):
        storage.restore_backup(journal, destination)

    assert not destination.exists()
    assert not list(tmp_path.glob(".restored.sav.*.tmp"))
    assert backup.read_bytes() == synthetic_save

    monkeypatch.undo()
    receipt = storage.restore_backup(journal, destination)
    assert receipt.output_path == destination
    assert destination.read_bytes() == synthetic_save
