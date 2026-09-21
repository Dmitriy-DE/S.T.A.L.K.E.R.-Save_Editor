"""Opt-in, non-blocking diagnostics submission UI."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout

from editor.diagnostics import submit_logs


class DiagnosticsWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.completed.emit(submit_logs())
        except Exception as exc:  # pragma: no cover - defensive thread boundary
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class DiagnosticsDialog(QDialog):
    """Let the user send bounded local logs and show the opaque report id."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Диагностика Save Editor")
        self.setModal(True)
        self._worker: DiagnosticsWorker | None = None

        layout = QVBoxLayout(self)
        description = QLabel(
            "Отправятся только технические логи с ограниченным размером. "
            "Сейвы и их содержимое не отправляются; локальные пути обезличиваются."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.status_label = QLabel("Готово к отправке")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.send_button = QPushButton("Отправить логи")
        self.send_button.clicked.connect(self._send)
        layout.addWidget(self.send_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _send(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.send_button.setEnabled(False)
        self.status_label.setText("Собираю и отправляю логи…")
        worker = DiagnosticsWorker(self)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(lambda: self._clear_worker(worker))
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _clear_worker(self, worker: DiagnosticsWorker) -> None:
        if self._worker is worker:
            self._worker = None

    def _on_completed(self, report_id: str) -> None:
        self.status_label.setText(f"Логи отправлены. Номер отчёта: {report_id}")
        self.send_button.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.status_label.setText(f"Логи не отправлены: {message}")
        self.send_button.setEnabled(True)


__all__ = ["DiagnosticsDialog", "DiagnosticsWorker"]
