from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeGuard

from save_format import SaveError

from .models import EditPlan, PreparedEdit


@dataclass(frozen=True)
class ExportReceipt:
    """Receipt returned only after the destination has been read back."""

    output_path: Path
    backup_path: Path
    output_sha256: str


BackupStatus = Literal["verified", "missing", "corrupt"]


@dataclass(frozen=True)
class BackupRecord:
    """One journal entry and the result of checking its recovery bytes."""

    journal_path: Path
    backup_path: Path
    created_at: str
    source_path: str
    source_sha256: str
    output_path: str | None
    output_sha256: str | None
    operation: dict[str, object]
    status: BackupStatus
    actual_sha256: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RestoreReceipt:
    """Receipt returned after a verified backup restore and read-back."""

    output_path: Path
    backup_path: Path
    output_sha256: str
    safety_backup_path: Path | None = None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _write_exclusive(path: Path, data: bytes) -> None:
    """Write a new file without allowing an existing path to be replaced."""

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


def _write_backup(path: Path, data: bytes) -> None:
    _write_exclusive(path, data)


def _write_journal(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _write_exclusive(path, encoded)


def _make_temp_path(directory: Path, output_name: str) -> Path:
    fd, name = tempfile.mkstemp(
        prefix=f".{output_name}.", suffix=".tmp", dir=str(directory)
    )
    os.close(fd)
    return Path(name)


def _write_temp_bytes(path: Path, data: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _publish_noreplace(temp_path: Path, destination: Path) -> None:
    """Publish by creating a hard link, which fails atomically if destination exists."""

    try:
        os.link(temp_path, destination)
    except FileExistsError as exc:
        raise SaveError(f"Output уже существует: {destination}") from exc
    except OSError as exc:
        raise SaveError(f"Атомарная публикация output не удалась: {exc}") from exc
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _fsync_directory(directory: Path) -> None:
    """Best-effort directory durability; Windows may not expose directory handles."""

    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _rewrite_journal(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    temp_path = _make_temp_path(path.parent, path.name)
    try:
        _write_temp_bytes(temp_path, encoded)
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _backup_path(source_path: Path, backup_dir: Path) -> Path:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    token = uuid.uuid4().hex
    stem = source_path.stem or "save"
    return backup_dir / f"{stem}_{stamp}_{token}_ORIGINAL.sav"


def _operation_summary(plan: EditPlan) -> dict[str, object]:
    return {
        "money": plan.money,
        "stack_count": len(plan.stacks),
        "move_count": len(plan.moves),
        "detach_count": len(plan.detach),
        "attach_count": len(plan.attach),
        "raw_count": len(plan.raw),
        "add_count": len(plan.adds),
        "upgrade_count": len(plan.upgrades),
        "durability_count": len(plan.durability),
        "relation_count": len(plan.faction_relations),
        "player_faction": plan.player_faction is not None,
    }


def _is_sha256(value: object) -> TypeGuard[str]:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _journal_backup_path(journal_path: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("backup_path must be a non-empty string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = journal_path.parent / path
    return path


def _record(
    *,
    journal_path: Path,
    backup_path: Path,
    created_at: str = "",
    source_path: str = "",
    source_sha256: str = "",
    output_path: str | None = None,
    output_sha256: str | None = None,
    operation: dict[str, object] | None = None,
    status: BackupStatus = "corrupt",
    actual_sha256: str | None = None,
    error: str | None = None,
) -> BackupRecord:
    return BackupRecord(
        journal_path=journal_path,
        backup_path=backup_path,
        created_at=created_at,
        source_path=source_path,
        source_sha256=source_sha256,
        output_path=output_path,
        output_sha256=output_sha256,
        operation=dict(operation or {}),
        status=status,
        actual_sha256=actual_sha256,
        error=error,
    )


def inspect_backup(journal_path: Path) -> BackupRecord:
    """Read and hash-check one backup journal without changing any file.

    A journal is considered usable only when it is version 1, has the final
    ``verified`` status, and its referenced backup bytes match the recorded
    source SHA256.  Missing bytes and malformed/mismatched metadata remain
    visible to the UI as explicit non-restorable states.
    """

    journal_path = Path(journal_path).expanduser()
    fallback_backup = journal_path.with_suffix(".sav")
    try:
        payload = json.loads(journal_path.read_text("utf-8"))
    except FileNotFoundError:
        return _record(
            journal_path=journal_path,
            backup_path=fallback_backup,
            error="Journal отсутствует",
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _record(
            journal_path=journal_path,
            backup_path=fallback_backup,
            error=f"Journal не читается: {exc}",
        )

    if not isinstance(payload, dict):
        return _record(
            journal_path=journal_path,
            backup_path=fallback_backup,
            error="Journal должен содержать JSON object",
        )

    try:
        if payload.get("version") != 1:
            raise ValueError("неподдерживаемая версия journal")
        backup_path = _journal_backup_path(journal_path, payload.get("backup_path"))
        source_sha256 = payload.get("source_sha256")
        if not _is_sha256(source_sha256):
            raise ValueError("source_sha256 имеет неверный формат")
        status = payload.get("status")
        if status != "verified":
            raise ValueError(f"journal status={status!r} не является verified")
        created_at = payload.get("created_at", "")
        source_path = payload.get("source_path", "")
        output_path = payload.get("output_path")
        output_sha256 = payload.get("output_sha256")
        operation = payload.get("operation", {})
        if not isinstance(created_at, str) or not created_at.strip():
            raise ValueError("created_at должен быть строкой")
        if not isinstance(source_path, str) or not source_path.strip():
            raise ValueError("source_path должен быть строкой")
        if not isinstance(output_path, str) or not output_path.strip():
            raise ValueError("output_path должен быть непустой строкой")
        if not _is_sha256(output_sha256):
            raise ValueError("output_sha256 имеет неверный формат")
        if not isinstance(operation, dict):
            raise ValueError("operation должен быть JSON object")
    except (TypeError, ValueError) as exc:
        return _record(
            journal_path=journal_path,
            backup_path=fallback_backup,
            error=f"Journal повреждён: {exc}",
        )

    try:
        data = backup_path.read_bytes()
    except FileNotFoundError:
        return _record(
            journal_path=journal_path,
            backup_path=backup_path,
            created_at=created_at,
            source_path=source_path,
            source_sha256=source_sha256,
            output_path=output_path,
            output_sha256=output_sha256,
            operation=operation,
            status="missing",
            error="Backup-файл отсутствует",
        )
    except OSError as exc:
        return _record(
            journal_path=journal_path,
            backup_path=backup_path,
            created_at=created_at,
            source_path=source_path,
            source_sha256=source_sha256,
            output_path=output_path,
            output_sha256=output_sha256,
            operation=operation,
            error=f"Backup не читается: {exc}",
        )

    actual_sha256 = _sha256(data)
    if actual_sha256 != source_sha256.lower():
        return _record(
            journal_path=journal_path,
            backup_path=backup_path,
            created_at=created_at,
            source_path=source_path,
            source_sha256=source_sha256.lower(),
            output_path=output_path,
            output_sha256=output_sha256,
            operation=operation,
            actual_sha256=actual_sha256,
            error=(
                "Backup SHA256 не совпал: "
                f"expected={source_sha256.lower()} actual={actual_sha256}"
            ),
        )
    return _record(
        journal_path=journal_path,
        backup_path=backup_path,
        created_at=created_at,
        source_path=source_path,
        source_sha256=source_sha256.lower(),
        output_path=output_path,
        output_sha256=output_sha256.lower() if isinstance(output_sha256, str) else None,
        operation=operation,
        status="verified",
        actual_sha256=actual_sha256,
    )


def list_backups(backup_dirs: Iterable[Path]) -> tuple[BackupRecord, ...]:
    """List journals and orphan original files from the supplied directories."""

    records: list[BackupRecord] = []
    known_backup_paths: set[str] = set()
    seen_journals: set[str] = set()
    directories: list[Path] = []
    for value in backup_dirs:
        directory = Path(value).expanduser()
        key = _canonical(directory)
        if key in {_canonical(item) for item in directories}:
            continue
        directories.append(directory)
        if not directory.is_dir():
            continue
        for journal_path in sorted(directory.glob("*.json")):
            journal_key = _canonical(journal_path)
            if journal_key in seen_journals:
                continue
            seen_journals.add(journal_key)
            record = inspect_backup(journal_path)
            records.append(record)
            known_backup_paths.add(_canonical(record.backup_path))

    for directory in directories:
        if not directory.is_dir():
            continue
        for backup_path in sorted(directory.glob("*_ORIGINAL.sav")):
            if _canonical(backup_path) in known_backup_paths:
                continue
            records.append(
                _record(
                    journal_path=backup_path.with_suffix(".json"),
                    backup_path=backup_path,
                    error="Для backup отсутствует journal",
                )
            )

    records.sort(key=lambda record: (record.created_at, str(record.journal_path)), reverse=True)
    return tuple(records)


def restore_backup(journal_or_record: Path | BackupRecord, output_path: Path) -> RestoreReceipt:
    """Restore one verified backup to a new, non-existing destination.

    Existing destinations are rejected before any write.  The backup and its
    journal remain untouched, so callers can retry with another path after an
    interrupted or failed restore.
    """

    record = (
        journal_or_record
        if isinstance(journal_or_record, BackupRecord)
        else inspect_backup(Path(journal_or_record))
    )
    if record.status != "verified":
        detail = f": {record.error}" if record.error else ""
        raise SaveError(f"Backup недоступен для восстановления ({record.status}){detail}")

    output_path = Path(output_path).expanduser()
    if _canonical(record.backup_path) == _canonical(output_path):
        raise SaveError("Output восстановления не может совпадать с backup")
    if os.path.lexists(output_path):
        raise SaveError(f"Output уже существует: {output_path}")
    if not output_path.parent.is_dir():
        raise SaveError(f"Папка output не существует: {output_path.parent}")

    try:
        data = record.backup_path.read_bytes()
    except OSError as exc:
        raise SaveError(f"Не удалось прочитать backup: {exc}") from exc
    actual_sha256 = _sha256(data)
    if actual_sha256 != record.source_sha256:
        raise SaveError(
            "Backup изменился после проверки: "
            f"expected={record.source_sha256} actual={actual_sha256}"
        )

    temp_path: Path | None = None
    published = False
    try:
        temp_path = _make_temp_path(output_path.parent, output_path.name)
        try:
            _write_temp_bytes(temp_path, data)
        except OSError as exc:
            raise SaveError(f"Не удалось записать временный restore: {exc}") from exc
        _publish_noreplace(temp_path, output_path)
        published = True
        _fsync_directory(output_path.parent)
        try:
            output_sha256 = _sha256(output_path.read_bytes())
        except OSError as exc:
            raise SaveError(f"Не удалось прочитать restored output: {exc}") from exc
        if output_sha256 != record.source_sha256:
            raise SaveError(
                "Restored output SHA256 не совпал: "
                f"expected={record.source_sha256} actual={output_sha256}"
            )
        return RestoreReceipt(
            output_path=output_path,
            backup_path=record.backup_path,
            output_sha256=output_sha256,
        )
    except SaveError:
        raise
    except OSError as exc:
        raise SaveError(f"Restore не удался: {exc}") from exc
    finally:
        if not published and temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


restore_local = restore_backup


def _publish_replace(temp_path: Path, destination: Path) -> None:
    """Atomically replace one explicitly selected existing destination."""

    try:
        os.replace(temp_path, destination)
    except OSError as exc:
        raise SaveError(f"Атомарная замена save не удалась: {exc}") from exc


def _prepared_output(prepared: PreparedEdit) -> tuple[bytes, str]:
    output_data = bytes(prepared.data)
    computed_output_sha = _sha256(output_data)
    if computed_output_sha != prepared.output_sha256:
        raise SaveError(
            "Prepared output SHA256 не совпадает с bytes: "
            f"expected={prepared.output_sha256} actual={computed_output_sha}"
        )
    return output_data, computed_output_sha


def _validate_local_source(source_path: Path, prepared: PreparedEdit) -> bytes:
    plan = prepared.plan
    if plan.source.kind != "local":
        raise SaveError("Запись в локальный сейв требует source kind=local")
    if _canonical(Path(plan.source.locator)) != _canonical(source_path):
        raise SaveError("Путь записи не совпадает с source locator из edit plan")
    if source_path.is_symlink():
        raise SaveError("Запись в symlink-сейв запрещена")
    if not source_path.is_file():
        raise SaveError(f"Исходный сейв не найден или не является файлом: {source_path}")
    try:
        source_data = source_path.read_bytes()
    except OSError as exc:
        raise SaveError(f"Не удалось прочитать source: {exc}") from exc
    source_sha = _sha256(source_data)
    if source_sha != plan.source.sha256:
        raise SaveError(
            "Источник изменился после анализа: "
            f"SHA256 expected={plan.source.sha256} actual={source_sha}"
        )
    return source_data


def replace_local(
    source_path: Path,
    prepared: PreparedEdit,
    backup_dir: Path,
) -> ExportReceipt:
    """Replace the selected local save after backup, atomic publish and read-back.

    This is deliberately separate from :func:`export_local`: callers must opt
    into replacing the exact analyzed source path.  The source SHA is checked
    before the backup and immediately before replacement; the existing source
    is never opened for partial writes.
    """

    source_path = Path(source_path).expanduser()
    backup_dir = Path(backup_dir).expanduser()
    output_data, computed_output_sha = _prepared_output(prepared)
    source_data = _validate_local_source(source_path, prepared)

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SaveError(f"Не удалось подготовить backup directory: {exc}") from exc

    backup_path = _backup_path(source_path, backup_dir)
    journal_path = backup_path.with_suffix(".json")
    temp_path: Path | None = None
    try:
        try:
            _write_backup(backup_path, source_data)
        except OSError as exc:
            raise SaveError(f"Не удалось создать backup: {exc}") from exc

        try:
            temp_path = _make_temp_path(source_path.parent, source_path.name)
            _write_temp_bytes(temp_path, output_data)
        except OSError as exc:
            raise SaveError(f"Не удалось записать временный output: {exc}") from exc

        payload: dict[str, object] = {
            "version": 1,
            "status": "prepared",
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "source_path": str(source_path),
            "source_sha256": _sha256(source_data),
            "output_path": str(source_path),
            "output_sha256": computed_output_sha,
            "backup_path": str(backup_path),
            "operation": {**_operation_summary(prepared.plan), "mode": "replace"},
        }
        try:
            _write_journal(journal_path, payload)
        except OSError as exc:
            raise SaveError(f"Не удалось записать journal: {exc}") from exc

        try:
            latest_source_sha = _sha256(source_path.read_bytes())
        except OSError as exc:
            raise SaveError(f"Не удалось повторно проверить source: {exc}") from exc
        if latest_source_sha != prepared.plan.source.sha256:
            raise SaveError(
                "Источник изменился перед атомарной заменой: "
                f"SHA256 expected={prepared.plan.source.sha256} actual={latest_source_sha}"
            )

        _publish_replace(temp_path, source_path)
        temp_path = None
        _fsync_directory(source_path.parent)
        try:
            published_sha = _sha256(source_path.read_bytes())
        except OSError as exc:
            raise SaveError(f"Не удалось прочитать replaced save: {exc}") from exc
        if published_sha != computed_output_sha:
            raise SaveError(
                "Replaced save read-back SHA256 не совпал: "
                f"expected={computed_output_sha} actual={published_sha}"
            )

        payload["status"] = "verified"
        _rewrite_journal(journal_path, payload)
        return ExportReceipt(
            output_path=source_path,
            backup_path=backup_path,
            output_sha256=published_sha,
        )
    except SaveError:
        raise
    except OSError as exc:
        raise SaveError(f"Замена локального сейва не удалась: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def restore_in_place(journal_or_record: Path | BackupRecord) -> RestoreReceipt:
    """Restore a verified backup to its recorded source slot in one atomic step.

    The current slot must still match the bytes recorded as the previous
    output.  Before replacing it, a second recovery backup is created, so an
    in-place rollback does not discard the state being rolled back.
    """

    record = (
        journal_or_record
        if isinstance(journal_or_record, BackupRecord)
        else inspect_backup(Path(journal_or_record))
    )
    if record.status != "verified":
        detail = f": {record.error}" if record.error else ""
        raise SaveError(f"Backup недоступен для восстановления ({record.status}){detail}")
    source_path = Path(record.source_path).expanduser()
    if not source_path.is_absolute():
        source_path = source_path.resolve(strict=False)
    if source_path.is_symlink():
        raise SaveError("Восстановление в symlink-сейв запрещено")
    if not source_path.parent.is_dir():
        raise SaveError(f"Папка source не существует: {source_path.parent}")
    if record.output_path is not None and _canonical(Path(record.output_path)) != _canonical(source_path):
        raise SaveError("Journal не относится к операции замены исходного слота")

    try:
        data = record.backup_path.read_bytes()
    except OSError as exc:
        raise SaveError(f"Не удалось прочитать backup: {exc}") from exc
    backup_sha = _sha256(data)
    if backup_sha != record.source_sha256:
        raise SaveError(
            "Backup изменился после проверки: "
            f"expected={record.source_sha256} actual={backup_sha}"
        )

    try:
        current_data = source_path.read_bytes()
    except FileNotFoundError:
        # A missing slot is safe to recreate with the existing no-replace
        # restore path; there is no current file to preserve first.
        return restore_backup(record, source_path)
    except OSError as exc:
        raise SaveError(f"Не удалось прочитать текущий слот: {exc}") from exc
    current_sha = _sha256(current_data)
    if record.output_sha256 is not None and current_sha != record.output_sha256:
        raise SaveError(
            "Текущий слот изменился после записи: "
            f"SHA256 expected={record.output_sha256} actual={current_sha}"
        )

    backup_dir = record.journal_path.parent
    safety_backup_path = _backup_path(source_path, backup_dir)
    safety_journal_path = safety_backup_path.with_suffix(".json")
    temp_path: Path | None = None
    try:
        try:
            _write_backup(safety_backup_path, current_data)
        except OSError as exc:
            raise SaveError(f"Не удалось создать safety backup: {exc}") from exc
        try:
            temp_path = _make_temp_path(source_path.parent, source_path.name)
            _write_temp_bytes(temp_path, data)
        except OSError as exc:
            raise SaveError(f"Не удалось записать временный restore: {exc}") from exc

        payload: dict[str, object] = {
            "version": 1,
            "status": "prepared",
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "source_path": str(source_path),
            "source_sha256": current_sha,
            "output_path": str(source_path),
            "output_sha256": record.source_sha256,
            "backup_path": str(safety_backup_path),
            "operation": {
                "mode": "restore",
                "restore_from": str(record.backup_path),
            },
        }
        try:
            _write_journal(safety_journal_path, payload)
        except OSError as exc:
            raise SaveError(f"Не удалось записать restore journal: {exc}") from exc

        try:
            latest_current_sha = _sha256(source_path.read_bytes())
        except OSError as exc:
            raise SaveError(f"Не удалось повторно проверить текущий слот: {exc}") from exc
        if latest_current_sha != current_sha:
            raise SaveError(
                "Текущий слот изменился перед восстановлением: "
                f"SHA256 expected={current_sha} actual={latest_current_sha}"
            )

        _publish_replace(temp_path, source_path)
        temp_path = None
        _fsync_directory(source_path.parent)
        try:
            output_sha256 = _sha256(source_path.read_bytes())
        except OSError as exc:
            raise SaveError(f"Не удалось прочитать restored slot: {exc}") from exc
        if output_sha256 != record.source_sha256:
            raise SaveError(
                "Restored slot SHA256 не совпал: "
                f"expected={record.source_sha256} actual={output_sha256}"
            )
        payload["status"] = "verified"
        _rewrite_journal(safety_journal_path, payload)
        return RestoreReceipt(
            output_path=source_path,
            backup_path=record.backup_path,
            output_sha256=output_sha256,
            safety_backup_path=safety_backup_path,
        )
    except SaveError:
        raise
    except OSError as exc:
        raise SaveError(f"Восстановление исходного слота не удалось: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def export_local(
    source_path: Path,
    output_path: Path,
    prepared: PreparedEdit,
    backup_dir: Path,
) -> ExportReceipt:
    """Export a prepared edit without mutating the source or overwriting output.

    The source is read again immediately before creating the backup and once
    more immediately before publication.  A stale or concurrently changed
    source therefore aborts before the destination is published.
    """

    source_path = Path(source_path).expanduser()
    output_path = Path(output_path).expanduser()
    backup_dir = Path(backup_dir).expanduser()
    plan = prepared.plan

    if plan.source.kind != "local":
        raise SaveError("Локальный export требует source kind=local")
    if _canonical(Path(plan.source.locator)) != _canonical(source_path):
        raise SaveError("Путь export не совпадает с source locator из edit plan")
    if _canonical(source_path) == _canonical(output_path):
        raise SaveError("Output не может совпадать с исходным сейвом")
    if os.path.lexists(output_path):
        raise SaveError(f"Output уже существует: {output_path}")
    if not output_path.parent.is_dir():
        raise SaveError(f"Папка output не существует: {output_path.parent}")

    output_data = bytes(prepared.data)
    computed_output_sha = _sha256(output_data)
    if computed_output_sha != prepared.output_sha256:
        raise SaveError(
            "Prepared output SHA256 не совпадает с bytes: "
            f"expected={prepared.output_sha256} actual={computed_output_sha}"
        )

    try:
        source_data = source_path.read_bytes()
    except OSError as exc:
        raise SaveError(f"Не удалось прочитать source: {exc}") from exc
    source_sha = _sha256(source_data)
    if source_sha != plan.source.sha256:
        raise SaveError(
            "Источник изменился после анализа: "
            f"SHA256 expected={plan.source.sha256} actual={source_sha}"
        )

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SaveError(f"Не удалось подготовить backup directory: {exc}") from exc
    backup_path = _backup_path(source_path, backup_dir)
    journal_path = backup_path.with_suffix(".json")
    try:
        try:
            _write_backup(backup_path, source_data)
        except OSError as exc:
            raise SaveError(f"Не удалось создать backup: {exc}") from exc

        temp_path = _make_temp_path(output_path.parent, output_path.name)
        try:
            try:
                _write_temp_bytes(temp_path, output_data)
            except OSError as exc:
                raise SaveError(f"Не удалось записать временный output: {exc}") from exc

            payload: dict[str, object] = {
                "version": 1,
                "status": "prepared",
                "created_at": dt.datetime.now(dt.UTC).isoformat(),
                "source_path": str(source_path),
                "source_sha256": source_sha,
                "output_path": str(output_path),
                "output_sha256": computed_output_sha,
                "backup_path": str(backup_path),
                "operation": _operation_summary(plan),
            }
            try:
                _write_journal(journal_path, payload)
            except OSError as exc:
                raise SaveError(f"Не удалось записать journal: {exc}") from exc

            try:
                latest_source_sha = _sha256(source_path.read_bytes())
            except OSError as exc:
                raise SaveError(f"Не удалось повторно проверить source: {exc}") from exc
            if latest_source_sha != plan.source.sha256:
                raise SaveError(
                    "Источник изменился перед публикацией: "
                    f"SHA256 expected={plan.source.sha256} actual={latest_source_sha}"
                )

            _publish_noreplace(temp_path, output_path)
            published = True
            _fsync_directory(output_path.parent)
            try:
                published_sha = _sha256(output_path.read_bytes())
            except OSError as exc:
                raise SaveError(f"Не удалось прочитать published output: {exc}") from exc
            if published_sha != computed_output_sha:
                raise SaveError(
                    "Output read-back SHA256 не совпал: "
                    f"expected={computed_output_sha} actual={published_sha}"
                )

            payload["status"] = "verified"
            _rewrite_journal(journal_path, payload)
            return ExportReceipt(
                output_path=output_path,
                backup_path=backup_path,
                output_sha256=published_sha,
            )
        finally:
            if not locals().get("published", False):
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
    except SaveError:
        raise
    except OSError as exc:
        raise SaveError(f"Local export не удался: {exc}") from exc
