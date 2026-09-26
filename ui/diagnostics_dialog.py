"""Opt-in, non-blocking diagnostics submission UI."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from editor.diagnostics import (
    Check,
    clear_crash_report,
    collect_log_bundle,
    export_log_bundle,
    format_report,
    run_checks,
    submit_logs,
)
from editor.i18n import tr

from .formatting import human_size
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import technical_details


class DiagnosticsWorker(QThread):
    previewed = Signal(int)
    completed = Signal(str)
    failed = Signal(str)

    def run(self) -> None:
        try:
            environment_report = format_report(run_checks())
            self.previewed.emit(len(collect_log_bundle(environment_report=environment_report)))
            self.completed.emit(submit_logs(environment_report=environment_report))
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


class EnvironmentCheckWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            self.completed.emit(run_checks())
        except Exception as exc:  # pragma: no cover - defensive thread boundary
            self.failed.emit(type(exc).__name__)


class EnvironmentDoctorDialog(QDialog):
    """Show grouped environment checks and let the user copy the same report."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("environmentDoctorDialog")
        self.setWindowTitle(tr("Проверка окружения"))
        self.resize(1050, 680)
        self.setModal(True)
        self._checks: tuple[Check, ...] = ()
        self._report_text = ""
        self._worker: EnvironmentCheckWorker | None = None

        layout = QVBoxLayout(self)
        self.status_label = QLabel(tr("Проверяю окружение…"), self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.table = QTreeWidget(self)
        self.table.setObjectName("environmentDoctorTable")
        self.table.setColumnCount(4)
        self.table.setHeaderLabels(
            [tr("Проверка"), tr("Статус"), tr("Подробности"), tr("Совет")]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setRootIsDecorated(True)
        self.table.setWordWrap(True)
        self.table.header().setStretchLastSection(True)
        for column, width in enumerate((350, 125, 260, 270)):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table, 1)

        self.copy_report_button = QPushButton(tr("Скопировать отчёт"), self)
        self.copy_report_button.setObjectName("environmentDoctorCopyReport")
        self.copy_report_button.setEnabled(False)
        self.copy_report_button.clicked.connect(self._copy_report)
        layout.addWidget(self.copy_report_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Закрыть"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._start_checks()

    def _start_checks(self) -> None:
        worker = EnvironmentCheckWorker(self)
        worker.completed.connect(self._show_results)
        worker.failed.connect(self._show_failure)
        worker.finished.connect(lambda: self._clear_worker(worker))
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _clear_worker(self, worker: EnvironmentCheckWorker) -> None:
        if self._worker is worker:
            self._worker = None

    def _show_results(self, value: object) -> None:
        checks = tuple(item for item in value if isinstance(item, Check)) if isinstance(value, list) else ()
        self._checks = checks
        self._report_text = format_report(checks)
        groups: dict[str, QTreeWidgetItem] = {}
        status_names = {
            "ok": tr("ОК"),
            "warn": tr("Предупреждение"),
            "fail": tr("Ошибка"),
        }
        for check in checks:
            group = groups.get(check.group)
            if group is None:
                group = QTreeWidgetItem(self.table, [check.group])
                group.setExpanded(True)
                groups[check.group] = group
            row = QTreeWidgetItem(
                group,
                [
                    check.name,
                    status_names[check.status],
                    check.detail,
                    check.hint,
                ],
            )
            for column in range(4):
                row.setToolTip(column, row.text(column))
        self.status_label.setText(tr("Проверок выполнено: {0}", len(checks)))
        self.copy_report_button.setEnabled(bool(checks))

    def _show_failure(self, error_type: str) -> None:
        self.status_label.setText(tr("Не удалось выполнить проверки: {0}", error_type))

    def _copy_report(self) -> None:
        system_clipboard = QApplication.clipboard()
        if system_clipboard is None:
            self.status_label.setText(tr("Буфер обмена недоступен"))
            return
        system_clipboard.setText(self._report_text)
        self.status_label.setText(tr("Отчёт скопирован"))


class DiagnosticsDialog(QDialog):
    """Let the user send bounded local logs and show the opaque report id."""

    def __init__(self, parent=None, *, after_crash: bool = False) -> None:
        super().__init__(parent)
        self.setMinimumWidth(520)  # titles and buttons were clipped at the default width
        self._after_crash = after_crash
        self.setWindowTitle(tr("Диагностика Save Editor"))
        self.setModal(True)
        self._worker: DiagnosticsWorker | None = None
        self._export_worker: DiagnosticsExportWorker | None = None
        self._technical_detail_text = ""
        self._details_dialog: TechnicalDetailsDialog | None = None

        layout = QVBoxLayout(self)
        description = QLabel(
            tr("Отправятся обезличенные журналы и отчёт проверки окружения. Сохранения и их содержимое не отправляются.")
        )
        description.setWordWrap(True)
        if after_crash:
            crash_note = QLabel(
                tr("В прошлый раз редактор закрылся из-за ошибки. Отправь отчёт — это поможет её исправить.")
            )
            crash_note.setWordWrap(True)
            crash_note.setObjectName("diagnosticsCrashNote")
            layout.addWidget(crash_note)
        layout.addWidget(description)
        self.preview_label = QLabel(
            tr("Перед отправкой будут подготовлены журналы и отчёт проверки окружения.")
        )
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)
        self.status_label = QLabel(tr("Готово к отправке"))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setVisible(False)
        layout.addWidget(self.details_label)
        self.details_button = QPushButton(tr("Технические детали"))
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self._toggle_details)
        layout.addWidget(self.details_button)
        self.send_button = QPushButton(tr("Отправить журналы и отчёт"))
        self.send_button.clicked.connect(self._send)
        layout.addWidget(self.send_button)
        self.export_button = QPushButton(tr("Экспортировать обезличенные журналы"))
        self.export_button.clicked.connect(self._export)
        layout.addWidget(self.export_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Закрыть"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _send(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.send_button.setEnabled(False)
        self.status_label.setText(tr("Собираю и отправляю журналы…"))
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
            tr("Экспорт обезличенных журналов"),
            "save-editor-diagnostics.log.gz",
            tr("Архив журналов (*.log.gz)"),
        )
        if not filename:
            return
        self.export_button.setEnabled(False)
        self.status_label.setText(tr("Сохраняю локальный экспорт журналов…"))
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
        self.preview_label.setText(tr("Обезличенный отчёт подготовлен ({0}).", human_size(size)))

    def done(self, result: int) -> None:
        if self._after_crash:
            # Offered once: sent or dismissed, the same crash is not raised again.
            clear_crash_report()
        super().done(result)

    def _on_completed(self, report_id: str) -> None:
        self.status_label.setText(tr("Журналы отправлены. Номер отчёта: {0}", report_id))
        self._set_details("")
        self.send_button.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.status_label.setText(tr("Не удалось отправить журналы. Попробуй позже."))
        self._set_details(message)
        self.send_button.setEnabled(True)

    def _on_export_completed(self, path: str) -> None:
        self.status_label.setText(tr("Обезличенные журналы экспортированы."))
        self._set_details(tr("Путь к файлу: {0}", path))
        self.export_button.setEnabled(True)

    def _on_export_failed(self, message: str) -> None:
        self.status_label.setText(tr("Не удалось экспортировать журналы."))
        self._set_details(message)
        self.export_button.setEnabled(True)

    def _set_details(self, value: str) -> None:
        self._technical_detail_text = technical_details(value)
        self.details_label.setText(self._technical_detail_text)
        visible = bool(value)
        self.details_button.setVisible(visible)
        self.details_label.setVisible(visible and not self.details_label.isHidden())
        if not visible:
            self.details_button.setText(tr("Технические детали"))

    def _toggle_details(self) -> None:
        if not self._technical_detail_text:
            return
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(self._technical_detail_text, self)
        self._details_dialog.open()


__all__ = [
    "DiagnosticsDialog",
    "DiagnosticsExportWorker",
    "DiagnosticsWorker",
    "EnvironmentCheckWorker",
    "EnvironmentDoctorDialog",
]
