from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import editor.storage as storage
import save_format as sf
from editor.models import EditPlan, SourceRef
from editor.prepare import prepare_edit


def _prepared(tmp_path: Path, data: bytes, *, money: int = 900_000):
    source = tmp_path / "сейв источник.sav"
    source.write_bytes(data)
    plan = EditPlan(
        source=SourceRef(
            kind="local",
            locator=str(source),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        money=money,
    )
    return source, prepare_edit(data, plan)


def test_export_local_creates_unique_backup_journal_and_unicode_output(
    tmp_path: Path, synthetic_save: bytes
) -> None:
    source, prepared = _prepared(tmp_path, synthetic_save)
    destination_dir = tmp_path / "папка назначения"
    destination_dir.mkdir()
    output = destination_dir / "edited копия.sav"
    backup_dir = tmp_path / "backup"

    receipt = storage.export_local(source, output, prepared, backup_dir)

    assert receipt.output_path == output
    assert receipt.output_sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
    assert output.read_bytes() == prepared.data
    assert source.read_bytes() == synthetic_save
    assert receipt.backup_path.read_bytes() == synthetic_save

    journal = receipt.backup_path.with_suffix(".json")
    payload = json.loads(journal.read_text("utf-8"))
    assert payload["source_sha256"] == hashlib.sha256(synthetic_save).hexdigest()
    assert payload["output_sha256"] == receipt.output_sha256
    assert payload["backup_path"] == str(receipt.backup_path)
    assert payload["operation"]["money"] == 900_000


def test_export_local_rejects_same_path_and_existing_output(
    tmp_path: Path, synthetic_save: bytes
) -> None:
    source, prepared = _prepared(tmp_path, synthetic_save)
    backup_dir = tmp_path / "backup"

    with pytest.raises(sf.SaveError, match="same|исход"):
        storage.export_local(source, source, prepared, backup_dir)
    assert list(backup_dir.glob("*")) == []

    output = tmp_path / "already exists.sav"
    old = b"keep this output"
    output.write_bytes(old)
    with pytest.raises(sf.SaveError, match="exist|существ"):
        storage.export_local(source, output, prepared, backup_dir)
    assert output.read_bytes() == old
    assert list(backup_dir.glob("*")) == []


def test_export_local_rejects_changed_source_before_backup_or_output(
    tmp_path: Path, synthetic_save: bytes
) -> None:
    source, prepared = _prepared(tmp_path, synthetic_save)
    source.write_bytes(synthetic_save + b"changed")
    output = tmp_path / "edited.sav"
    backup_dir = tmp_path / "backup"

    with pytest.raises(sf.SaveError, match="SHA256"):
        storage.export_local(source, output, prepared, backup_dir)
    assert not output.exists()
    assert not backup_dir.exists()


def test_export_local_backup_failure_leaves_source_and_no_output(
    tmp_path: Path, synthetic_save: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, prepared = _prepared(tmp_path, synthetic_save)
    output = tmp_path / "edited.sav"
    backup_dir = tmp_path / "backup"

    def fail_backup(path: Path, data: bytes) -> None:
        path.write_bytes(data[:7])
        raise OSError("injected backup failure")

    monkeypatch.setattr(storage, "_write_backup", fail_backup)
    with pytest.raises(sf.SaveError, match="backup|резерв"):
        storage.export_local(source, output, prepared, backup_dir)
    assert source.read_bytes() == synthetic_save
    assert not output.exists()
    assert list(backup_dir.glob("*.sav"))


def test_export_local_partial_temp_failure_is_cleaned_and_backup_kept(
    tmp_path: Path, synthetic_save: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, prepared = _prepared(tmp_path, synthetic_save)
    output = tmp_path / "edited.sav"
    backup_dir = tmp_path / "backup"

    def fail_temp(path: Path, data: bytes) -> None:
        path.write_bytes(data[:11])
        raise OSError("injected partial temp failure")

    monkeypatch.setattr(storage, "_write_temp_bytes", fail_temp)
    with pytest.raises(sf.SaveError, match="temp|временн"):
        storage.export_local(source, output, prepared, backup_dir)
    assert source.read_bytes() == synthetic_save
    assert not output.exists()
    assert list(backup_dir.glob("*.sav"))
    assert not list(tmp_path.glob(".edited.sav.*.tmp"))


def test_export_local_journal_failure_does_not_publish_output(
    tmp_path: Path, synthetic_save: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, prepared = _prepared(tmp_path, synthetic_save)
    output = tmp_path / "edited.sav"
    backup_dir = tmp_path / "backup"

    def fail_journal(path: Path, payload: dict[str, object]) -> None:
        raise OSError("injected journal failure")

    monkeypatch.setattr(storage, "_write_journal", fail_journal)
    with pytest.raises(sf.SaveError, match="journal|журнал"):
        storage.export_local(source, output, prepared, backup_dir)
    assert source.read_bytes() == synthetic_save
    assert not output.exists()
    assert list(backup_dir.glob("*.sav"))


def test_export_local_backups_are_unique_within_one_second(
    tmp_path: Path, synthetic_save: bytes
) -> None:
    source, prepared = _prepared(tmp_path, synthetic_save)
    backup_dir = tmp_path / "backup"

    first = storage.export_local(source, tmp_path / "one.sav", prepared, backup_dir)
    second = storage.export_local(source, tmp_path / "two.sav", prepared, backup_dir)

    assert first.backup_path != second.backup_path
    assert first.backup_path.read_bytes() == second.backup_path.read_bytes() == synthetic_save


def test_export_local_noreplace_race_preserves_racing_output(
    tmp_path: Path, synthetic_save: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, prepared = _prepared(tmp_path, synthetic_save)
    output = tmp_path / "edited.sav"
    backup_dir = tmp_path / "backup"
    real_publish = storage._publish_noreplace

    def race(temp_path: Path, destination: Path) -> None:
        destination.write_bytes(b"racing writer")
        real_publish(temp_path, destination)

    monkeypatch.setattr(storage, "_publish_noreplace", race)
    with pytest.raises(sf.SaveError, match="exist|существ"):
        storage.export_local(source, output, prepared, backup_dir)
    assert output.read_bytes() == b"racing writer"
    assert source.read_bytes() == synthetic_save
