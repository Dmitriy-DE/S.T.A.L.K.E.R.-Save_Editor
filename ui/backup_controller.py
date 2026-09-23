"""Backup journal browser and safe local restore controls for the Qt shell."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from editor.service import EditorService
from editor.storage import BackupRecord, RestoreReceipt, inspect_backup, list_backups

_STATUS_TEXT = {
    "verified": "Проверено",
    "missing": "Отсутствует",
    "corrupt": "Повреждено",
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
            self.progress.emit("Восстановление: проверка backup…")
            if self.in_place:
                receipt = self.service.restore_in_place(self.record)
            else:
                if self.destination is None:
                    raise ValueError("Для restore copy не задан destination")
                receipt = self.service.restore_local(self.record, self.destination)
            self.progress.emit("Восстановление: output проверен по SHA256")
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
        self._status_text = "Выбери запись журнала для проверки"

    @property
    def records(self) -> tuple[BackupRecord, ...]:
        return self._records

    def refresh(self) -> None:
        self._records = list_backups(self.backup_dirs)
        self._preview_record = None
        self.clear_error()
        self.set_progress(f"Найдено записей: {len(self._records)}; файлы не изменены")
        self.records_changed.emit(self._records)

    @staticmethod
    def _hash_text(value: str) -> str:
        return f"{value[:12]}…" if value else "—"

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
        return ", ".join(parts) or "без изменений"

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
            self.set_progress("Выбери запись журнала для проверки")
            return None
        checked = inspect_backup(record.journal_path)
        self._preview_record = checked if checked.status == "verified" else None
        if checked.status != "verified":
            detail = checked.error or "Backup недоступен"
            self.set_error(f"Restore запрещён: {_STATUS_TEXT[checked.status]} — {detail}")
            return None
        self.set_progress(
            f"Проверка копии готова: backup {checked.backup_path.name}; "
            f"SHA256 {checked.source_sha256}; размер {checked.backup_path.stat().st_size} B. "
            "Можно создать новую копию или явно откатить исходный слот."
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

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)

    def set_progress(self, message: str) -> None:
        self._status_text = message
        self.progress_changed.emit(message)

    def set_error(self, message: str) -> None:
        self.error_changed.emit(message)
        self.set_progress("Восстановление остановлено")

    def clear_error(self) -> None:
        self.error_changed.emit("")

    def mark_restored(self, receipt: RestoreReceipt) -> None:
        self.refresh()
        self.set_progress(
            f"Копия восстановлена: {receipt.output_path}; "
            f"SHA256 {receipt.output_sha256}"
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
            f"Исходный слот восстановлен: {receipt.output_path}; "
            f"SHA256 {receipt.output_sha256}{safety}"
        )
        self._preview_record = None
        self.restored_in_place.emit(receipt)

    @property
    def busy(self) -> bool:
        return self._busy


__all__ = ["BackupController", "RestoreWorker"]
