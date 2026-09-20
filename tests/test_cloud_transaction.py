from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from editor.cloud_capabilities import (
    CloudWriteCapability,
    CloudWriteNotAttemptedError,
)
from editor.models import EditPlan, SourceRef
from editor.prepare import prepare_edit
from editor.transactions import CloudTransactionError, upload_cloud

REMOTE_PATH = "Stalker2/Saved/STEAM/SaveGames/Data/slot.sav"


class FakeCloud:
    def __init__(self, data: bytes, *, mode: str = "verified") -> None:
        self.files = {REMOTE_PATH: data}
        self.original = data
        self.mode = mode
        self.read_calls: list[str] = []
        self.write_calls: list[tuple[str, bytes]] = []
        self.sync_calls = 0
        self.wait_calls: list[tuple[str, int, int]] = []
        self.write_capability = CloudWriteCapability(True, "fake writer ready")

    def read_file(self, filename: str) -> bytes:
        self.read_calls.append(filename)
        if filename != REMOTE_PATH:
            raise RuntimeError(f"wrong slot: {filename}")
        if self.mode == "read_error":
            raise RuntimeError("read failed")
        if self.mode == "readback_mismatch" and len(self.read_calls) > 1:
            return b"different remote bytes"
        return self.files[filename]

    def write_file(self, filename: str, data: bytes) -> None:
        if self.mode == "write_not_attempted":
            raise CloudWriteNotAttemptedError("writer disappeared before request")
        self.write_calls.append((filename, data))
        if filename != REMOTE_PATH:
            raise RuntimeError(f"wrong slot: {filename}")
        self.files[filename] = data
        if self.mode == "write_error":
            raise RuntimeError("write failed after send")

    def sync(self) -> None:
        self.sync_calls += 1
        if self.mode == "sync_error":
            raise RuntimeError("sync failed")

    def wait_persisted(self, filename: str, expected_size: int, timeout: int = 120) -> bool:
        self.wait_calls.append((filename, expected_size, timeout))
        return self.mode != "persist_timeout"


def _prepared(synthetic_save: bytes):
    source = SourceRef(
        kind="cloud",
        locator=REMOTE_PATH,
        sha256=hashlib.sha256(synthetic_save).hexdigest(),
    )
    return prepare_edit(synthetic_save, EditPlan(source=source, money=900_000))


def test_verified_upload_creates_backup_and_recovery_and_uses_exact_source_locator(
    synthetic_save: bytes, tmp_path: Path
) -> None:
    prepared = _prepared(synthetic_save)
    worker = FakeCloud(synthetic_save)

    receipt = upload_cloud(worker, prepared, tmp_path, persisted_timeout=7)

    assert receipt.status == "verified"
    assert receipt.remote_path == REMOTE_PATH
    assert receipt.reason is None
    assert receipt.output_sha256 == hashlib.sha256(prepared.data).hexdigest()
    assert receipt.backup_path.read_bytes() == synthetic_save
    assert receipt.recovery_path.read_bytes() == prepared.data
    assert worker.read_calls == [REMOTE_PATH, REMOTE_PATH]
    assert len(worker.write_calls) == 1
    assert worker.write_calls[0] == (REMOTE_PATH, prepared.data)
    assert worker.wait_calls == [(REMOTE_PATH, len(prepared.data), 7)]


def test_stale_source_aborts_before_write(synthetic_save: bytes, tmp_path: Path) -> None:
    prepared = _prepared(synthetic_save)
    worker = FakeCloud(b"changed source")

    with pytest.raises(CloudTransactionError, match="изменился"):
        upload_cloud(worker, prepared, tmp_path)

    assert worker.write_calls == []
    assert list(tmp_path.iterdir()) == []


def test_wrong_slot_is_rejected_before_write(synthetic_save: bytes, tmp_path: Path) -> None:
    prepared = _prepared(synthetic_save)
    worker = FakeCloud(synthetic_save)
    wrong_plan = EditPlan(
        source=SourceRef(
            kind="cloud",
            locator="Stalker2/Saved/STEAM/SaveGames/Data/other.sav",
            sha256=hashlib.sha256(synthetic_save).hexdigest(),
        ),
        money=900_000,
    )
    prepared = prepare_edit(synthetic_save, wrong_plan)

    with pytest.raises(CloudTransactionError, match="ReadFile"):
        upload_cloud(worker, prepared, tmp_path)

    assert worker.write_calls == []


def test_backup_failure_aborts_before_write(synthetic_save: bytes, tmp_path: Path) -> None:
    prepared = _prepared(synthetic_save)
    worker = FakeCloud(synthetic_save)
    backup_path = tmp_path / "backup-file"
    backup_path.write_bytes(b"not a directory")

    with pytest.raises(CloudTransactionError, match="backup"):
        upload_cloud(worker, prepared, backup_path)

    assert worker.write_calls == []


@pytest.mark.parametrize("advertised", [False, None])
def test_read_only_or_unadvertised_transport_is_rejected_before_any_io(
    synthetic_save: bytes,
    tmp_path: Path,
    advertised: bool | None,
) -> None:
    prepared = _prepared(synthetic_save)
    worker = FakeCloud(synthetic_save)
    if advertised is False:
        worker.write_capability = CloudWriteCapability(False, "Steam web read-only")
        expected = "Steam web read-only"
    else:
        del worker.write_capability
        expected = "не подтверждает"

    with pytest.raises(CloudTransactionError, match=expected):
        upload_cloud(worker, prepared, tmp_path)

    assert worker.read_calls == []
    assert worker.write_calls == []
    assert list(tmp_path.iterdir()) == []


def test_definite_write_refusal_is_not_reported_as_uncertain(
    synthetic_save: bytes,
    tmp_path: Path,
) -> None:
    prepared = _prepared(synthetic_save)
    worker = FakeCloud(synthetic_save, mode="write_not_attempted")

    with pytest.raises(CloudTransactionError, match="writer disappeared"):
        upload_cloud(worker, prepared, tmp_path)

    assert worker.write_calls == []


def test_write_failure_is_uncertain_and_does_not_retry(synthetic_save: bytes, tmp_path: Path) -> None:
    prepared = _prepared(synthetic_save)
    worker = FakeCloud(synthetic_save, mode="write_error")

    receipt = upload_cloud(worker, prepared, tmp_path)

    assert receipt.status == "uncertain"
    assert "WriteFile" in (receipt.reason or "")
    assert receipt.recovery_path.read_bytes() == prepared.data
    assert len(worker.write_calls) == 1
    assert worker.sync_calls == 0


@pytest.mark.parametrize("mode", ["sync_error", "persist_timeout"])
def test_sync_or_persist_timeout_is_uncertain_with_recovery(
    synthetic_save: bytes, tmp_path: Path, mode: str
) -> None:
    prepared = _prepared(synthetic_save)
    worker = FakeCloud(synthetic_save, mode=mode)

    receipt = upload_cloud(worker, prepared, tmp_path)

    assert receipt.status == "uncertain"
    assert receipt.recovery_path.read_bytes() == prepared.data
    assert len(worker.write_calls) == 1
    assert worker.sync_calls == 1


def test_readback_sha_mismatch_is_uncertain_without_second_write(
    synthetic_save: bytes, tmp_path: Path
) -> None:
    prepared = _prepared(synthetic_save)
    worker = FakeCloud(synthetic_save, mode="readback_mismatch")

    receipt = upload_cloud(worker, prepared, tmp_path)

    assert receipt.status == "uncertain"
    assert "read-back SHA" in (receipt.reason or "")
    assert len(worker.write_calls) == 1
    assert receipt.recovery_path.exists()
