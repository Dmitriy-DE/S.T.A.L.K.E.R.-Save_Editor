"""Fail-closed cloud upload transaction.

The transport is deliberately small and injectable.  This module owns the
ordering and recovery artifacts; SteamWorker remains an IPC implementation.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .cloud_capabilities import (
    CloudWriteCapability,
    CloudWriteNotAttemptedError,
    cloud_write_capability,
)
from .models import CloudReceipt, PreparedEdit
from .steam_profiles import (
    is_editor_cloud_artifact,
    steam_cloud_profile_for_app_id,
    steam_cloud_profiles,
)


class CloudTransactionError(RuntimeError):
    """Raised when an upload can be rejected before any remote write."""


class CloudTransport(Protocol):
    @property
    def write_capability(self) -> CloudWriteCapability: ...

    def read_file(self, filename: str) -> bytes: ...

    def write_file(self, filename: str, data: bytes) -> None: ...

    def sync(self) -> None: ...

    def wait_persisted(self, filename: str, expected_size: int, timeout: int = 120) -> bool: ...

    def list_files(self) -> object: ...


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_stem(remote_path: str) -> str:
    leaf = remote_path.replace("\\", "/").rsplit("/", 1)[-1]
    stem = Path(leaf).stem or "cloud-save"
    clean = re.sub(r"[^0-9A-Za-zА-Яа-яёЁ._-]+", "_", stem).strip("._")
    return (clean or "cloud-save")[:80]


def _artifact_paths(remote_path: str, backup_dir: Path) -> tuple[Path, Path]:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    token = uuid.uuid4().hex
    stem = _safe_stem(remote_path)
    prefix = f"{stem}_{stamp}_{token}"
    return (
        backup_dir / f"{prefix}_ORIGINAL.sav",
        backup_dir / f"{prefix}_EDITED.sav",
    )


def _write_exclusive(path: Path, data: bytes) -> None:
    fd: int | None = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def _notify(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback is None:
        return
    try:
        callback(stage)
    except Exception:
        # Progress reporting cannot turn a completed transaction into a false
        # failure.  The caller still receives the receipt from the protocol.
        return


def _uncertain(
    remote_path: str,
    backup_path: Path,
    recovery_path: Path,
    output_sha256: str,
    reason: str,
) -> CloudReceipt:
    return CloudReceipt(
        status="uncertain",
        remote_path=remote_path,
        backup_path=backup_path,
        recovery_path=recovery_path,
        output_sha256=output_sha256,
        reason=reason,
    )


def _validate_cloud_target(worker: CloudTransport, remote_path: str) -> None:
    """Enforce the release path contract at the transaction boundary."""

    if is_editor_cloud_artifact(remote_path):
        raise CloudTransactionError(
            f"Cloud upload запрещён для editor recovery artifact: {remote_path}"
        )
    accepted = tuple(
        profile for profile in steam_cloud_profiles() if profile.accepts(remote_path)
    )
    if not accepted:
        raise CloudTransactionError(
            "Cloud upload запрещён: remote path не относится к сохранению "
            "поддержанного Steam Cloud профиля"
        )

    # Real Steam workers expose the connected app id.  Match it here so a
    # valid-looking path from another game cannot be written merely because
    # the UI selected it.  Injectable test transports may omit app_id and are
    # still covered by the profile allow-list above.
    app_id = getattr(worker, "app_id", None)
    if app_id is None:
        return
    try:
        profile = steam_cloud_profile_for_app_id(int(app_id))
    except (KeyError, TypeError, ValueError) as exc:
        raise CloudTransactionError(
            f"Cloud upload запрещён: неизвестный Steam app_id={app_id!r}"
        ) from exc
    if not profile.accepts(remote_path):
        raise CloudTransactionError(
            f"Cloud upload запрещён: path не принадлежит подключённой игре "
            f"{profile.release_id!r}: {remote_path}"
        )


def upload_cloud(
    worker: CloudTransport,
    prepared: PreparedEdit,
    backup_dir: Path,
    *,
    persisted_timeout: int = 120,
    on_stage: Callable[[str], None] | None = None,
) -> CloudReceipt:
    """Upload one prepared edit and return verified or explicitly uncertain.

    The exact remote locator comes from ``prepared.plan.source``.  A fresh
    download and SHA check happen before artifacts and before ``WriteFile``;
    after ``WriteFile`` every failure is ambiguous and therefore never retried.
    """

    source = prepared.plan.source
    if source.kind != "cloud":
        raise CloudTransactionError("Cloud upload требует source kind=cloud")
    remote_path = source.locator
    _validate_cloud_target(worker, remote_path)
    edited = bytes(prepared.data)
    output_sha256 = _sha256(edited)
    if output_sha256 != prepared.output_sha256:
        raise CloudTransactionError(
            "Prepared output SHA256 не совпадает с bytes: "
            f"expected={prepared.output_sha256} actual={output_sha256}"
        )

    capability = cloud_write_capability(worker)
    if not capability.writable:
        raise CloudTransactionError(
            f"Cloud upload недоступен до WriteFile: {capability.reason}"
        )

    _notify(on_stage, "fresh_read")
    try:
        fresh = bytes(worker.read_file(remote_path))
    except Exception as exc:
        raise CloudTransactionError(f"ReadFile до WriteFile не удался: {exc}") from exc
    fresh_sha256 = _sha256(fresh)
    if fresh_sha256 != source.sha256:
        raise CloudTransactionError(
            "Cloud source изменился после анализа: "
            f"SHA256 expected={source.sha256} actual={fresh_sha256}"
        )

    backup_dir = Path(backup_dir).expanduser()
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CloudTransactionError(f"Не удалось подготовить backup directory: {exc}") from exc
    backup_path, recovery_path = _artifact_paths(remote_path, backup_dir)
    try:
        _write_exclusive(backup_path, fresh)
    except OSError as exc:
        raise CloudTransactionError(f"Не удалось создать cloud backup: {exc}") from exc
    _notify(on_stage, "backup_created")
    try:
        _write_exclusive(recovery_path, edited)
    except OSError as exc:
        raise CloudTransactionError(f"Не удалось создать edited recovery: {exc}") from exc
    _notify(on_stage, "recovery_created")

    try:
        worker.write_file(remote_path, edited)
    except CloudWriteNotAttemptedError as exc:
        raise CloudTransactionError(f"WriteFile не запускался: {exc}") from exc
    except Exception as exc:
        return _uncertain(
            remote_path,
            backup_path,
            recovery_path,
            output_sha256,
            f"WriteFile result uncertain after request: {exc}",
        )
    _notify(on_stage, "write_sent")

    try:
        worker.sync()
    except Exception as exc:
        return _uncertain(
            remote_path,
            backup_path,
            recovery_path,
            output_sha256,
            f"SyncCloudFiles failed after WriteFile; result uncertain: {exc}",
        )
    _notify(on_stage, "sync_requested")

    try:
        persisted = bool(
            worker.wait_persisted(
                remote_path,
                len(edited),
                timeout=persisted_timeout,
            )
        )
    except Exception as exc:
        return _uncertain(
            remote_path,
            backup_path,
            recovery_path,
            output_sha256,
            f"persisted=true check failed after WriteFile; result uncertain: {exc}",
        )
    if not persisted:
        return _uncertain(
            remote_path,
            backup_path,
            recovery_path,
            output_sha256,
            "persisted=true не подтверждён после WriteFile; результат uncertain",
        )
    _notify(on_stage, "persisted")

    readback_method = getattr(worker, "readback_file", None)
    readback_reader = readback_method if callable(readback_method) else worker.read_file
    try:
        readback = bytes(readback_reader(remote_path))
    except Exception as exc:
        return _uncertain(
            remote_path,
            backup_path,
            recovery_path,
            output_sha256,
            f"ReadFile read-back failed after WriteFile; result uncertain: {exc}",
        )
    readback_sha256 = _sha256(readback)
    if readback_sha256 != output_sha256:
        return _uncertain(
            remote_path,
            backup_path,
            recovery_path,
            output_sha256,
            "cloud read-back SHA mismatch after WriteFile; result uncertain",
        )
    _notify(on_stage, "readback_verified")
    return CloudReceipt(
        status="verified",
        remote_path=remote_path,
        backup_path=backup_path,
        recovery_path=recovery_path,
        output_sha256=output_sha256,
    )
