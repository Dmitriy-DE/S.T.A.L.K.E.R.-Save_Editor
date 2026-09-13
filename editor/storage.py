from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from save_format import SaveError

from .models import EditPlan, PreparedEdit


@dataclass(frozen=True)
class ExportReceipt:
    """Receipt returned only after the destination has been read back."""

    output_path: Path
    backup_path: Path
    output_sha256: str


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
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
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
    }


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
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
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
