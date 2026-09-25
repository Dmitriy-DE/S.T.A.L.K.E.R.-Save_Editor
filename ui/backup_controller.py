"""Backup journal browser and safe local restore controls for the Qt shell."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from editor.i18n import tr
from editor.service import EditorService
from editor.storage import BackupRecord, RestoreReceipt, inspect_backup, list_backups

_STATUS_TEXT = {
    "verified": tr("Проверено"),
    "missing": tr("Отсутствует"),
    "corrupt": tr("Повреждено"),
}


class RestoreWorker(QThread):
    """Run the potentially large backup copy outside the Qt UI thread."""

    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        service: EditorService,
        record: BackupRecord,
        destination: Path | None = None,
        *,
        in_place: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.record = record
        self.destination = Path(destination) if destination is not None else None
        self.in_place = in_place

    def run(self) -> None:
        try:
            self.progress.emit(tr("Восстановление: проверка backup…"))
            if self.in_place:
                receipt = self.service.restore_in_place(self.record)
            else:
                if self.destination is None:
                    raise ValueError(tr("Для restore copy не задан destination"))
                receipt = self.service.restore_local(self.record, self.destination)
            self.progress.emit(tr("Восстановление: output проверен по SHA256"))
            self.completed.emit(receipt)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class BackupController(QObject):
    """Own backup journal inspection and restore state without a legacy page."""

    records_changed = Signal(object)
    progress_changed = Signal(str)
    error_changed = Signal(str)
    busy_changed = Signal(bool)
    restored = Signal(object)
    restored_in_place = Signal(object)

    def __init__(
        self,
        backup_dirs: Sequence[Path] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.backup_dirs = tuple(Path(path).expanduser() for path in (backup_dirs or ()))
        self._records: tuple[BackupRecord, ...] = ()
        self._preview_record: BackupRecord | None = None
        self._busy = False
        self._status_text = tr("Выбери запись журнала для проверки")

    @property
    def records(self) -> tuple[BackupRecord, ...]:
        return self._records

    def refresh(self) -> None:
        self._records = list_backups(self.backup_dirs)
        self._preview_record = None
        self.clear_error()
        self.set_progress(tr("Найдено записей: {0}; файлы не изменены", len(self._records)))
        self.records_changed.emit(self._records)

    @staticmethod
    @staticmethod
    def _operation_text(operation: dict[str, object]) -> str:
        parts: list[str] = []
        mode = operation.get("mode")
        if mode:
            parts.append(str(mode))
        if operation.get("money") is not None:
            parts.append(f"money={operation['money']}")
        for key in (
            "stack_count",
            "move_count",
            "detach_count",
            "attach_count",
            "raw_count",
            "add_count",
            "upgrade_count",
            "durability_count",
            "relation_count",
        ):
            value = operation.get(key)
            if value:
                parts.append(f"{key}={value}")
        if operation.get("player_faction"):
            parts.append("player_faction")
        return ", ".join(parts) or tr("без изменений")

    @staticmethod
    def _can_restore_in_place(record: BackupRecord) -> bool:
        if not record.source_path.strip() or not record.output_path:
            return False
        try:
            source = Path(record.source_path).expanduser().resolve(strict=False)
            output = Path(record.output_path).expanduser().resolve(strict=False)
        except OSError:
            return False
        return source == output

    def preview_restore(self, record: BackupRecord | None) -> BackupRecord | None:
        self._preview_record = None
        if record is None:
            self.set_progress(tr("Выбери запись журнала для проверки"))
            return None
        checked = inspect_backup(record.journal_path)
        self._preview_record = checked if checked.status == "verified" else None
        if checked.status != "verified":
            detail = checked.error or tr("Backup недоступен")
            self.set_error(tr("Restore запрещён: {0} — {1}", _STATUS_TEXT[checked.status], detail))
            return None
        self.set_progress(
            tr("Проверка копии готова: backup {0}; SHA256 {1}; размер {2} B. Можно создать новую копию или явно откатить исходный слот.", checked.backup_path.name, checked.source_sha256, checked.backup_path.stat().st_size)
        )
        return checked

    @property
    def status_text(self) -> str:
        return self._status_text

    def clear_preview(self) -> None:
        self._preview_record = None

    @staticmethod
    def can_restore_in_place(record: BackupRecord) -> bool:
        return BackupController._can_restore_in_place(record)

    @property
    def preview_record(self) -> BackupRecord | None:
        return self._preview_record

    def folder_for(self, record: BackupRecord | None = None) -> Path:
        return record.journal_path.parent if record is not None else (
            self.backup_dirs[0] if self.backup_dirs else Path.cwd()
        )

    @staticmethod
    def default_restore_destination(record: BackupRecord) -> Path:
        """Choose a recoverable, non-destructive copy name for a verified backup."""

        source = Path(record.source_path).expanduser()
        return source.with_name(f"{source.stem}-restored{source.suffix or '.sav'}")

    def set_review_records(self, records: Sequence[BackupRecord]) -> None:
        """Load deterministic records for a visual review without touching disk."""

        self._records = tuple(records)
        self._preview_record = None
        self.records_changed.emit(self._records)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)

    def set_progress(self, message: str) -> None:
        self._status_text = message
        self.progress_changed.emit(message)

    def set_error(self, message: str) -> None:
        self.error_changed.emit(message)
        self.set_progress(tr("Восстановление остановлено"))

    def clear_error(self) -> None:
        self.error_changed.emit("")

    def mark_restored(self, receipt: RestoreReceipt) -> None:
        self.refresh()
        self.set_progress(
            tr("Копия восстановлена: {0}; SHA256 {1}", receipt.output_path, receipt.output_sha256)
        )
        self._preview_record = None
        self.restored.emit(receipt)

    def mark_in_place_restored(self, receipt: RestoreReceipt) -> None:
        self.refresh()
        safety = (
            f"; safety backup: {receipt.safety_backup_path}"
            if receipt.safety_backup_path is not None
            else ""
        )
        self.set_progress(
            tr("Исходный слот восстановлен: {0}; SHA256 {1}{2}", receipt.output_path, receipt.output_sha256, safety)
        )
        self._preview_record = None
        self.restored_in_place.emit(receipt)

    @property
    def busy(self) -> bool:
        return self._busy


__all__ = ["BackupController", "RestoreWorker"]
