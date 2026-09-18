"""Qt Steam Cloud source selection and fail-closed upload states."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

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

from editor.capabilities import FormatCapabilities
from editor.formats import FormatDetectionError
from editor.models import CloudReceipt, PreparedEdit
from editor.platforms import backup_dirs
from editor.service import EditorService
from editor.steam_backend import make_cloud_worker
from editor.transactions import CloudTransport
from save_format import SaveError, SaveInfo
from steam_cloud import APP_ID, SAVE_PREFIX, CloudFile, discover_helper


class CloudSession(CloudTransport, Protocol):
    """A transport this view also owns the lifecycle of.

    ``editor.transactions.CloudTransport`` only describes what an upload needs.
    The Cloud tab additionally starts, connects and closes the helper process,
    so the widget-level contract is stated here instead of being assumed.
    """

    def start(self) -> None: ...

    def connect(self, app_id: int) -> None: ...

    def close(self) -> None: ...


WorkerFactory = Callable[[Path], CloudSession]
HelperFinder = Callable[[], Path | None]


@dataclass(frozen=True)
class CloudSnapshot:
    """Immutable remote bytes and inspection result for the selected Data save."""

    name: str
    data: bytes
    info: SaveInfo
    file: CloudFile
    format_id: str = "stalker2"
    format_title: str = "S.T.A.L.K.E.R. 2: Heart of Chornobyl"
    release_id: str = "stalker2"
    edition: str = "s2"
    capabilities: FormatCapabilities = field(
        default_factory=lambda: FormatCapabilities(
            read_inventory=True,
            edit_money=True,
            edit_stacks=True,
            experimental_fields=frozenset({"edit_money"}),
        )
    )


class CloudOperationWorker(QThread):
    """Run helper lifecycle, remote reads, and upload transactions off the UI thread."""

    completed = Signal(object)
    transport_ready = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        service: EditorService,
        *,
        mode: str,
        helper_path: Path | None = None,
        transport: CloudSession | None = None,
        worker_factory: WorkerFactory = make_cloud_worker,
        cloud_file: CloudFile | None = None,
        prepared: PreparedEdit | None = None,
        backup_dir: Path | None = None,
        app_id: int = APP_ID,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.mode = mode
        self.helper_path = helper_path
        self.transport = transport
        self.worker_factory = worker_factory
        self.cloud_file = cloud_file
        self.prepared = prepared
        self.backup_dir = backup_dir
        self.app_id = app_id

    def run(self) -> None:
        created_transport = False
        transport = self.transport
        try:
            if self.mode == "list":
                # A helper is optional: the native worker needs no AppImage.
                # The factory tries native first and only needs the helper path
                # for its fallback, so pass it through even when absent.
                self.progress.emit("Steam Cloud: подключение…")
                transport = self.worker_factory(self.helper_path)
                created_transport = True
                transport.start()
                transport.connect(self.app_id)
                files = transport.list_files()
                self.transport_ready.emit(transport)
                self.completed.emit(files)
                return

            if transport is None:
                raise SaveError("Steam Cloud не подключён; сначала нажми «Подключить и обновить»")

            if self.mode == "analyze":
                cloud_file = self.cloud_file
                if cloud_file is None:
                    raise SaveError("Cloud save не выбран")
                self.progress.emit(f"Cloud: скачивание {cloud_file.name}…")
                data = bytes(transport.read_file(cloud_file.name))
                result = self.service.inspect_result(
                    data,
                    with_inventory=True,
                    source_name=cloud_file.name,
                )
                self.completed.emit(
                    CloudSnapshot(
                        cloud_file.name,
                        data,
                        result.info,
                        cloud_file,
                        result.format_id,
                        result.format_title,
                        result.release_id,
                        result.edition,
                        result.capabilities,
                    )
                )
                return

            if self.mode == "upload":
                if self.prepared is None or self.backup_dir is None:
                    raise SaveError("Для cloud upload нужен проверенный preview")
                self.progress.emit("Cloud: fresh read и SHA…")
                receipt = self.service.upload_cloud(
                    transport,
                    self.prepared,
                    self.backup_dir,
                    persisted_timeout=180,
                    on_stage=self.progress.emit,
                )
                self.completed.emit(receipt)
                return

            raise SaveError(f"Неизвестный cloud operation: {self.mode}")
        except FormatDetectionError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            if created_transport and transport is not None:
                try:
                    transport.close()
                except Exception:
                    pass
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class CloudView(QWidget):
    """Connect explicitly, select a Data save, and display upload certainty."""

    files_ready = Signal(object)
    snapshot_ready = Signal(object)
    upload_ready = Signal(object)
    operation_failed = Signal(str)
    operation_progress = Signal(str)
    busy_changed = Signal(bool)

    PATH_COLUMN = 0
    SIZE_COLUMN = 1
    TIMESTAMP_COLUMN = 2
    PERSISTED_COLUMN = 3

    def __init__(
        self,
        service: EditorService,
        *,
        worker_factory: WorkerFactory = make_cloud_worker,
        helper_finder: HelperFinder = discover_helper,
        helper_path: Path | None = None,
        backup_dir: Path | None = None,
        app_id: int = APP_ID,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.worker_factory = worker_factory
        self.helper_finder = helper_finder
        self.helper_path = (
            Path(helper_path).expanduser()
            if helper_path is not None
            else self.helper_finder()
        )
        if self.helper_path is not None:
            self.helper_path = self.helper_path.expanduser()
        self.backup_dir = (
            Path(backup_dir).expanduser()
            if backup_dir is not None
            else backup_dirs()[0]
        )
        self.app_id = app_id
        self.transport: CloudSession | None = None
        self._files: tuple[CloudFile, ...] = ()
        self._snapshot: CloudSnapshot | None = None
        self._prepared: PreparedEdit | None = None
        self._thread: CloudOperationWorker | None = None
        self._build_ui()

    @property
    def files(self) -> tuple[CloudFile, ...]:
        return self._files

    @property
    def snapshot(self) -> CloudSnapshot | None:
        return self._snapshot

    @property
    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        helper_form = QFormLayout()
        helper_row = QHBoxLayout()
        self.helper_edit = QLineEdit(str(self.helper_path) if self.helper_path else "")
        self.helper_edit.setPlaceholderText("Путь к SteamCloudFileManager")
        helper_row.addWidget(self.helper_edit, 1)
        self.choose_helper_button = QPushButton("Выбрать…")
        self.choose_helper_button.clicked.connect(self._choose_helper)
        helper_row.addWidget(self.choose_helper_button)
        helper_form.addRow("Steam helper", helper_row)
        layout.addLayout(helper_form)

        actions = QHBoxLayout()
        self.connect_button = QPushButton("Подключить и обновить")
        self.connect_button.clicked.connect(self.start_connect)
        actions.addWidget(self.connect_button)
        self.analyze_button = QPushButton("Скачать и анализировать")
        self.analyze_button.setEnabled(False)
        self.analyze_button.clicked.connect(self.analyze_selected)
        actions.addWidget(self.analyze_button)
        self.upload_button = QPushButton("Загрузить выбранный preview")
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.start_upload)
        actions.addWidget(self.upload_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.status_label = QLabel("Steam Cloud: не подключён")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Data path", "Размер", "Timestamp", "Persisted"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

        self.result_label = QLabel("Cloud write не запускался")
        self.result_label.setWordWrap(True)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result_label)
        self.progress_label = QLabel("")
        self.progress_label.setWordWrap(True)
        layout.addWidget(self.progress_label)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #a11;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

    def _choose_helper(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Выбрать SteamCloudFileManager",
            str(self.helper_path.parent if self.helper_path else ""),
            "Steam helper (*.exe *.AppImage *);;Все файлы (*)",
        )
        if filename:
            self.helper_path = Path(filename).expanduser()
            self.helper_edit.setText(str(self.helper_path))

    def _resolve_helper(self) -> Path | None:
        value = self.helper_edit.text().strip()
        if value:
            self.helper_path = Path(value).expanduser()
            return self.helper_path
        found = self.helper_finder()
        if found is not None:
            self.helper_path = Path(found).expanduser()
            self.helper_edit.setText(str(self.helper_path))
        return self.helper_path

    def _refuse_while_busy(self) -> bool:
        """Report a declined action instead of returning silently.

        The buttons are disabled while an operation runs, so this path is
        reached by keyboard and by automation - where a control that does
        nothing and says nothing looks exactly like a broken one.
        """

        if not self.is_busy:
            return False
        self.status_label.setText("Steam Cloud: дождись завершения текущей операции")
        return True

    def _start_worker(self, worker: CloudOperationWorker) -> None:
        if self.is_busy:
            return
        self._thread = worker
        self._thread.transport_ready.connect(self._on_transport_ready)
        self._thread.progress.connect(self._on_progress)
        self._thread.failed.connect(self._on_failed)
        self._thread.finished.connect(self._on_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self.set_busy(True)
        worker.start()

    def start_connect(self) -> None:
        if self._refuse_while_busy():
            return
        helper = self._resolve_helper()
        if helper is None:
            self._on_failed("SteamCloudFileManager не найден; укажи helper явно")
            return
        self._close_transport()
        self.clear_error()
        self.status_label.setText("Steam Cloud: подключение…")
        worker = CloudOperationWorker(
            self.service,
            mode="list",
            helper_path=helper,
            worker_factory=self.worker_factory,
            app_id=self.app_id,
            parent=self,
        )
        worker.completed.connect(self._on_files_ready)
        self._start_worker(worker)

    def selected_file(self) -> CloudFile | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._files):
            return self._files[row]
        return None

    def analyze_selected(self) -> None:
        if self._refuse_while_busy():
            return
        cloud_file = self.selected_file()
        if cloud_file is None:
            self._on_failed("Сначала выбери Data/*.sav в cloud списке")
            return
        if self.transport is None:
            self._on_failed("Steam Cloud не подключён; запись не выполнялась")
            return
        self.clear_error()
        worker = CloudOperationWorker(
            self.service,
            mode="analyze",
            transport=self.transport,
            cloud_file=cloud_file,
            worker_factory=self.worker_factory,
            parent=self,
        )
        worker.completed.connect(self._on_snapshot_ready)
        self._start_worker(worker)

    def set_prepared(self, prepared: PreparedEdit | None) -> None:
        self._prepared = None
        if prepared is None:
            self.upload_button.setEnabled(False)
            return
        selected = self.selected_file()
        source = prepared.plan.source
        if source.kind != "cloud" or selected is None or source.locator != selected.name:
            self.result_label.setText("Preview не относится к выбранному cloud Data path; upload запрещён")
            self.upload_button.setEnabled(False)
            return
        self._prepared = prepared
        self.result_label.setText(
            f"Cloud preview готов для {selected.name}; SHA {prepared.output_sha256[:12]}…"
        )
        self.upload_button.setEnabled(self.transport is not None and not self.is_busy)

    def start_upload(self) -> None:
        if self._refuse_while_busy():
            return
        selected = self.selected_file()
        prepared = self._prepared
        if self.transport is None:
            self._on_failed("Steam Cloud не подключён; upload не выполнялся")
            return
        if prepared is None or selected is None:
            self._on_failed("Сначала выбери cloud slot и создай его preview")
            return
        if prepared.plan.source.kind != "cloud" or prepared.plan.source.locator != selected.name:
            self._on_failed("Выбранный cloud slot не совпадает с preview; WriteFile не выполнялся")
            return
        self.clear_error()
        worker = CloudOperationWorker(
            self.service,
            mode="upload",
            transport=self.transport,
            prepared=prepared,
            backup_dir=self.backup_dir,
            worker_factory=self.worker_factory,
            parent=self,
        )
        worker.completed.connect(self._on_upload_ready)
        self._start_worker(worker)

    def _on_transport_ready(self, transport: CloudSession) -> None:
        self.transport = transport

    def _on_files_ready(self, files) -> None:
        self._files = tuple(
            cloud_file
            for cloud_file in files
            if isinstance(cloud_file, CloudFile)
            and cloud_file.name.startswith(SAVE_PREFIX)
            and cloud_file.name.lower().endswith(".sav")
        )
        self._snapshot = None
        self._prepared = None
        self.table.setRowCount(len(self._files))
        for row, cloud_file in enumerate(self._files):
            values = (
                cloud_file.name,
                f"{cloud_file.size} B",
                str(cloud_file.timestamp),
                "да" if cloud_file.is_persisted else "нет",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.clearSelection()
        self._on_selection_changed()
        self.status_label.setText(
            f"Steam Cloud: подключено · {len(self._files)} Data/*.sav"
            if self._files
            else "Steam Cloud: подключено · 0 Data/*.sav (список пуст)"
        )
        self.files_ready.emit(self._files)

    def _on_snapshot_ready(self, snapshot: CloudSnapshot) -> None:
        self._snapshot = snapshot
        self._prepared = None
        self.result_label.setText(
            f"Cloud snapshot: {snapshot.name}; CRC={'OK' if snapshot.info.crc_ok else 'FAIL'}; "
            f"SHA256 {snapshot.info.sha256}"
        )
        self.status_label.setText("Cloud save скачан и проанализирован; staged preview ещё не создан")
        self.snapshot_ready.emit(snapshot)

    def _on_upload_ready(self, receipt: CloudReceipt) -> None:
        self._prepared = None
        self.upload_button.setEnabled(False)
        if receipt.status == "verified":
            self.result_label.setText(
                "Cloud verified: persisted=true и read-back SHA совпали. "
                f"Original backup: {receipt.backup_path}; recovery: {receipt.recovery_path}"
            )
            self.status_label.setText("Cloud: verified")
        else:
            self.result_label.setText(
                "Cloud uncertain: WriteFile уже отправлен, но результат не подтверждён. "
                f"Причина: {receipt.reason}. Original backup: {receipt.backup_path}; "
                f"recovery: {receipt.recovery_path}. Повторный WriteFile запрещён."
            )
            self.status_label.setText("Cloud: uncertain — требуется reconciliation")
        self.upload_ready.emit(receipt)

    def _on_selection_changed(self) -> None:
        self._snapshot = None
        self._prepared = None
        self.upload_button.setEnabled(False)
        self.analyze_button.setEnabled(self.selected_file() is not None and self.transport is not None)

    def _on_progress(self, message: str) -> None:
        self.progress_label.setText(message)
        self.operation_progress.emit(message)

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Cloud operation не выполнена; WriteFile мог не запускаться")
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.operation_failed.emit(message)

    def _on_finished(self) -> None:
        self._thread = None
        self.set_busy(False)
        self.analyze_button.setEnabled(self.selected_file() is not None and self.transport is not None)
        self.operation_progress.emit("Cloud operation завершена")

    def set_busy(self, busy: bool) -> None:
        for widget in (
            self.connect_button,
            self.choose_helper_button,
            self.helper_edit,
            self.table,
            self.analyze_button,
            self.upload_button,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self.analyze_button.setEnabled(self.selected_file() is not None and self.transport is not None)
            self.upload_button.setEnabled(self._prepared is not None and self.transport is not None)
        self.busy_changed.emit(busy)

    def set_external_busy(self, busy: bool) -> None:
        """Disable cloud controls while an unrelated local operation runs."""

        if self.is_busy:
            return
        self.connect_button.setEnabled(not busy)
        self.choose_helper_button.setEnabled(not busy)
        self.helper_edit.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self.analyze_button.setEnabled(not busy and self.selected_file() is not None and self.transport is not None)
        self.upload_button.setEnabled(not busy and self._prepared is not None and self.transport is not None)

    def clear_error(self) -> None:
        self.error_label.clear()
        self.error_label.setVisible(False)

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.progress_label.setText("Cloud operation остановлена")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Never let a running worker outlive the widget.

        Qt aborts the process when a QThread is destroyed while it is still
        running.  A close during a cloud operation - or a test tearing the view
        down - used to risk exactly that.
        """

        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(10_000)
        self._close_transport()
        super().closeEvent(event)

    def _close_transport(self) -> None:
        transport, self.transport = self.transport, None
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass

    def close_transport(self) -> None:
        if not self.is_busy:
            self._close_transport()


__all__ = ["CloudOperationWorker", "CloudSnapshot", "CloudView"]
