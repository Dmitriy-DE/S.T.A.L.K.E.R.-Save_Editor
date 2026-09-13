"""Backup journal browser and safe local restore controls for the Qt shell."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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
        destination: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.record = record
        self.destination = Path(destination)

    def run(self) -> None:
        try:
            self.progress.emit("Восстановление: проверка backup…")
            receipt = self.service.restore_local(self.record, self.destination)
            self.progress.emit("Восстановление: output проверен по SHA256")
            self.completed.emit(receipt)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class BackupView(QWidget):
    """Display journal/hash status and stage a restore to a new path."""

    restore_requested = Signal(object, object)
    choose_destination_requested = Signal()
    folder_open_requested = Signal(object)

    DATE_COLUMN = 0
    SOURCE_COLUMN = 1
    OPERATION_COLUMN = 2
    SHA_COLUMN = 3
    STATUS_COLUMN = 4

    def __init__(
        self,
        backup_dirs: Sequence[Path] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.backup_dirs = tuple(Path(path).expanduser() for path in (backup_dirs or ()))
        self._records: tuple[BackupRecord, ...] = ()
        self._preview_record: BackupRecord | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_button)
        self.open_folder_button = QPushButton("Открыть папку")
        self.open_folder_button.clicked.connect(self._open_folder)
        toolbar.addWidget(self.open_folder_button)
        toolbar.addStretch(1)
        self.directory_label = QLabel("; ".join(str(path) for path in self.backup_dirs) or "Папки backup не заданы")
        self.directory_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        toolbar.addWidget(self.directory_label, 1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Дата", "Источник", "Операция", "SHA256", "Статус"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)

        restore_form = QFormLayout()
        destination_row = QHBoxLayout()
        self.destination_edit = QLineEdit()
        self.destination_edit.setPlaceholderText("Новый путь для восстановленной копии .sav")
        self.destination_edit.textChanged.connect(self._destination_changed)
        destination_row.addWidget(self.destination_edit, 1)
        self.choose_destination_button = QPushButton("Выбрать…")
        self.choose_destination_button.clicked.connect(self._choose_destination)
        destination_row.addWidget(self.choose_destination_button)
        restore_form.addRow("Восстановить в", destination_row)
        layout.addLayout(restore_form)

        actions = QHBoxLayout()
        self.preview_button = QPushButton("Предпросмотр restore")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self.preview_restore)
        actions.addWidget(self.preview_button)
        self.restore_button = QPushButton("Восстановить копию")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._request_restore)
        actions.addWidget(self.restore_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.preview_label = QLabel("Выбери запись журнала для проверки")
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.preview_label)
        self.progress_label = QLabel("")
        self.progress_label.setWordWrap(True)
        layout.addWidget(self.progress_label)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #a11;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

    @property
    def records(self) -> tuple[BackupRecord, ...]:
        return self._records

    def refresh(self) -> None:
        self._records = list_backups(self.backup_dirs)
        self._preview_record = None
        self.table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            values = (
                record.created_at or "—",
                record.source_path or "Неизвестный источник",
                self._operation_text(record.operation),
                self._hash_text(record.source_sha256),
                _STATUS_TEXT[record.status],
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.clearSelection()
        self._selection_changed()
        self.clear_error()
        self.progress_label.setText(
            f"Найдено записей: {len(self._records)}; файлы не изменены"
        )

    @staticmethod
    def _hash_text(value: str) -> str:
        return f"{value[:12]}…" if value else "—"

    @staticmethod
    def _operation_text(operation: dict[str, object]) -> str:
        parts: list[str] = []
        if operation.get("money") is not None:
            parts.append(f"money={operation['money']}")
        for key in ("stack_count", "move_count", "detach_count", "attach_count", "raw_count"):
            value = operation.get(key)
            if value:
                parts.append(f"{key}={value}")
        return ", ".join(parts) or "без изменений"

    def selected_record(self) -> BackupRecord | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def _selection_changed(self) -> None:
        self._preview_record = None
        self.restore_button.setEnabled(False)
        record = self.selected_record()
        self.preview_button.setEnabled(record is not None)
        if record is None:
            self.preview_label.setText("Выбери запись журнала для проверки")
        else:
            detail = f"Статус: {_STATUS_TEXT[record.status]}"
            if record.error:
                detail += f" — {record.error}"
            self.preview_label.setText(detail)

    def preview_restore(self) -> None:
        record = self.selected_record()
        if record is None:
            return
        checked = inspect_backup(record.journal_path)
        self._preview_record = checked if checked.status == "verified" else None
        if checked.status != "verified":
            detail = checked.error or "Backup недоступен"
            self.preview_label.setText(f"Restore запрещён: {_STATUS_TEXT[checked.status]} — {detail}")
            self.restore_button.setEnabled(False)
            return
        self.preview_label.setText(
            f"Restore preview готов: backup {checked.backup_path.name}; "
            f"SHA256 {checked.source_sha256}; размер {checked.backup_path.stat().st_size} B. "
            "Будет создан новый файл, существующий путь не перезаписывается."
        )
        self._destination_changed()

    def _destination_changed(self) -> None:
        self.restore_button.setEnabled(
            self._preview_record is not None and bool(self.destination_edit.text().strip())
        )

    def _request_restore(self) -> None:
        if self._preview_record is None:
            return
        destination = self.destination_edit.text().strip()
        if destination:
            self.restore_requested.emit(self._preview_record, Path(destination).expanduser())

    def _choose_destination(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Путь восстановленной копии",
            "",
            "STALKER 2 save (*.sav);;Все файлы (*)",
        )
        if filename:
            self.destination_edit.setText(filename)

    def _open_folder(self) -> None:
        record = self.selected_record()
        path = record.journal_path.parent if record is not None else (
            self.backup_dirs[0] if self.backup_dirs else Path.cwd()
        )
        self.folder_open_requested.emit(path)

    def set_busy(self, busy: bool) -> None:
        for widget in (
            self.refresh_button,
            self.open_folder_button,
            self.table,
            self.choose_destination_button,
            self.destination_edit,
            self.preview_button,
            self.restore_button,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self.preview_button.setEnabled(self.selected_record() is not None)
            self._destination_changed()

    def set_progress(self, message: str) -> None:
        self.progress_label.setText(message)

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.progress_label.setText("Восстановление остановлено")

    def clear_error(self) -> None:
        self.error_label.clear()
        self.error_label.setVisible(False)

    def mark_restored(self, receipt: RestoreReceipt) -> None:
        self.refresh()
        self.preview_label.setText(
            f"Копия восстановлена: {receipt.output_path}; "
            f"SHA256 {receipt.output_sha256}"
        )
        self.progress_label.setText("Restore verified; backup и journal сохранены")
        self._preview_record = None
        self.restore_button.setEnabled(False)


__all__ = ["BackupView", "RestoreWorker"]
