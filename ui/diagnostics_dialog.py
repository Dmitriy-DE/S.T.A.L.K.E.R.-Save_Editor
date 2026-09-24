"""Opt-in, non-blocking diagnostics submission UI."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from editor.diagnostics import collect_log_bundle, export_log_bundle, submit_logs

from .formatting import human_size
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import technical_details


class DiagnosticsWorker(QThread):
    previewed = Signal(int)
    completed = Signal(str)
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.previewed.emit(len(collect_log_bundle()))
            self.completed.emit(submit_logs())
        except Exception as exc:  # pragma: no cover - defensive thread boundary
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class DiagnosticsExportWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, destination, parent=None) -> None:
        super().__init__(parent)
        self.destination = destination

    def run(self) -> None:
        try:
            self.completed.emit(str(export_log_bundle(self.destination)))
        except Exception as exc:  # pragma: no cover - defensive thread boundary
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class DiagnosticsDialog(QDialog):
    """Let the user send bounded local logs and show the opaque report id."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Диагностика Save Editor")
        self.setModal(True)
        self._worker: DiagnosticsWorker | None = None
        self._export_worker: DiagnosticsExportWorker | None = None
        self._technical_detail_text = ""
        self._details_dialog: TechnicalDetailsDialog | None = None

        layout = QVBoxLayout(self)
        description = QLabel(
            "Отправятся только обезличенные технические журналы ограниченного размера. "
            "Сохранения и их содержимое не отправляются."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.preview_label = QLabel(
            "Перед отправкой будет подготовлен архив обезличенных журналов."
        )
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)
        self.status_label = QLabel("Готово к отправке")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setVisible(False)
        layout.addWidget(self.details_label)
        self.details_button = QPushButton("Технические детали")
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self._toggle_details)
        layout.addWidget(self.details_button)
        self.send_button = QPushButton("Отправить журналы")
        self.send_button.clicked.connect(self._send)
        layout.addWidget(self.send_button)
        self.export_button = QPushButton("Экспортировать обезличенные журналы")
        self.export_button.clicked.connect(self._export)
        layout.addWidget(self.export_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _send(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.send_button.setEnabled(False)
        self.status_label.setText("Собираю и отправляю журналы…")
        worker = DiagnosticsWorker(self)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.previewed.connect(self._on_previewed)
        worker.finished.connect(lambda: self._clear_worker(worker))
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _export(self) -> None:
        if self._export_worker is not None and self._export_worker.isRunning():
            return
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Экспорт обезличенных журналов",
            "save-editor-diagnostics.log.gz",
            "Архив журналов (*.log.gz)",
        )
        if not filename:
            return
        self.export_button.setEnabled(False)
        self.status_label.setText("Сохраняю локальный экспорт журналов…")
        worker = DiagnosticsExportWorker(filename, self)
        worker.completed.connect(self._on_export_completed)
        worker.failed.connect(self._on_export_failed)
        worker.finished.connect(lambda: self._clear_export_worker(worker))
        worker.finished.connect(worker.deleteLater)
        self._export_worker = worker
        worker.start()

    def _clear_worker(self, worker: DiagnosticsWorker) -> None:
        if self._worker is worker:
            self._worker = None

    def _clear_export_worker(self, worker: DiagnosticsExportWorker) -> None:
        if self._export_worker is worker:
            self._export_worker = None

    def _on_previewed(self, size: int) -> None:
        self.preview_label.setText(f"Обезличенный архив подготовлен ({human_size(size)}).")

    def _on_completed(self, report_id: str) -> None:
        self.status_label.setText(f"Журналы отправлены. Номер отчёта: {report_id}")
        self._set_details("")
        self.send_button.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Не удалось отправить журналы. Попробуй позже.")
        self._set_details(message)
        self.send_button.setEnabled(True)

    def _on_export_completed(self, path: str) -> None:
        self.status_label.setText("Обезличенные журналы экспортированы.")
        self._set_details(f"Путь к файлу: {path}")
        self.export_button.setEnabled(True)

    def _on_export_failed(self, message: str) -> None:
        self.status_label.setText("Не удалось экспортировать журналы.")
        self._set_details(message)
        self.export_button.setEnabled(True)

    def _set_details(self, value: str) -> None:
        self._technical_detail_text = technical_details(value)
        self.details_label.setText(self._technical_detail_text)
        visible = bool(value)
        self.details_button.setVisible(visible)
        self.details_label.setVisible(visible and not self.details_label.isHidden())
        if not visible:
            self.details_button.setText("Технические детали")

    def _toggle_details(self) -> None:
        if not self._technical_detail_text:
            return
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(self._technical_detail_text, self)
        self._details_dialog.open()


__all__ = ["DiagnosticsDialog", "DiagnosticsExportWorker", "DiagnosticsWorker"]
