"""Small responsive Qt shell for local save inspection.

The window deliberately owns no parser or writer rules.  It asks
``EditorService`` to inspect bytes in a worker thread and keeps the last valid
snapshot visible when a later file is malformed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from editor.service import EditorService
from editor.models import EditPlan, PreparedEdit, SourceRef
from editor.platforms import backup_dirs
from save_format import SaveError, SaveInfo

from .changes_view import ChangesView
from .backups_view import BackupView, RestoreWorker
from .cloud_view import CloudSnapshot, CloudView
from .inventory_view import InventoryView
from .operation_worker import OperationWorker


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


@dataclass(frozen=True)
class LocalSnapshot:
    """Immutable bytes plus inspection result published to the UI thread."""

    path: Path
    data: bytes
    info: SaveInfo
    source_kind: str = "local"
    locator: str | None = None


class InspectWorker(QThread):
    """Run one local read/inspect operation outside the UI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: EditorService, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.path = path

    def run(self) -> None:
        try:
            data = self.path.read_bytes()
            info = self.service.inspect(data, with_inventory=True)
            self.completed.emit(LocalSnapshot(path=self.path, data=data, info=info))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    """Qt shell for local analysis, safe edits and local backup restore."""

    analysis_ready = Signal(object)
    analysis_failed = Signal(str)
    preview_ready = Signal(object)
    apply_ready = Signal(object)
    restore_ready = Signal(object)
    operation_failed = Signal(str)

    def __init__(self, service: EditorService) -> None:
        super().__init__()
        self.service = service
        self.snapshot: LocalSnapshot | None = None
        self.staged_counts: dict[int, int] = {}
        self.staged_money: int | None = None
        self.prepared_edit: PreparedEdit | None = None
        self.edit_actions_enabled = False
        self._inspect_thread: QThread | None = None
        self._inspect_worker: InspectWorker | None = None
        self._pending_path: Path | None = None
        self._operation_thread: QThread | None = None
        self._operation_kind: str | None = None
        self._cloud_busy = False

        self.setWindowTitle("S.T.A.L.K.E.R. 2 — Save Editor")
        self.resize(1100, 760)
        self.setMinimumSize(860, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        source_row = QHBoxLayout()
        self.open_button = QPushButton("Открыть .sav…")
        self.open_button.clicked.connect(self.open_local)
        source_row.addWidget(self.open_button)
        self.source_label = QLabel("Сейв не выбран")
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        source_row.addWidget(self.source_label, 1)
        layout.addLayout(source_row)

        self.status_label = QLabel("Готово к локальному анализу")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #a11;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "Обзор")
        self.tabs.addTab(self._build_inventory_tab(), "Инвентарь")
        self.tabs.addTab(self._build_changes_tab(), "Изменения")
        self.tabs.addTab(self._build_backups_tab(), "Резервные копии")
        self.tabs.addTab(self._build_cloud_tab(), "Steam Cloud")
        layout.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.preview_button = QPushButton("Предпросмотр")
        self.preview_button.setEnabled(False)
        self.preview_button.setToolTip("Подготовить immutable preview из staged edits")
        self.preview_button.clicked.connect(self._start_preview)
        actions.addWidget(self.preview_button)
        self.save_copy_button = QPushButton("Сохранить копию")
        self.save_copy_button.setEnabled(False)
        self.save_copy_button.setToolTip("Записать только ранее проверенный preview")
        self.save_copy_button.clicked.connect(self._choose_and_start_apply)
        actions.addWidget(self.save_copy_button)
        layout.addLayout(actions)

        self.setTabOrder(self.open_button, self.tabs)
        self.setTabOrder(self.tabs, self.preview_button)
        self.setTabOrder(self.preview_button, self.save_copy_button)

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.summary_label = QLabel("Открой локальный .sav для проверки CRC и структуры.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Сводка", self.summary_label)
        self.support_label = QLabel("Редактирование отключено до успешного анализа.")
        self.support_label.setWordWrap(True)
        form.addRow("Поддержка", self.support_label)

        money_box = QGroupBox("Баланс (staged до preview)")
        money_form = QFormLayout(money_box)
        self.money_status_label = QLabel("Баланс не определён")
        self.money_status_label.setWordWrap(True)
        money_form.addRow("Текущее → новое", self.money_status_label)
        money_row = QHBoxLayout()
        self.money_spin = QSpinBox()
        self.money_spin.setRange(0, 2_000_000_000)
        self.money_spin.setEnabled(False)
        self.money_spin.valueChanged.connect(self._on_money_value_changed)
        money_row.addWidget(self.money_spin)
        self.money_stage_button = QPushButton("Застейджить баланс")
        self.money_stage_button.setEnabled(False)
        self.money_stage_button.clicked.connect(self._stage_money)
        money_row.addWidget(self.money_stage_button)
        self.money_clear_button = QPushButton("Очистить")
        self.money_clear_button.setEnabled(False)
        self.money_clear_button.clicked.connect(self._clear_money)
        money_row.addWidget(self.money_clear_button)
        money_form.addRow("Новая сумма", money_row)
        form.addRow(money_box)
        return tab

    def _build_inventory_tab(self) -> QWidget:
        self.inventory_view = InventoryView(self)
        self.inventory_view.stage_requested.connect(self._stage_stack_change)
        self.inventory_view.clear_selected_requested.connect(self._clear_selected_stack)
        self.inventory_view.clear_all_requested.connect(self._clear_all_stacks)
        # Keep the old attribute available to small integrations while the
        # actual view now uses a stable-handle QAbstractTableModel.
        self.inventory_table = self.inventory_view.table
        self.inventory_model = self.inventory_view.model
        return self.inventory_view

    def _build_changes_tab(self) -> QWidget:
        self.changes_view = ChangesView(self)
        self.changes_view.preview_requested.connect(self._start_preview)
        self.changes_view.apply_requested.connect(self._choose_and_start_apply)
        self.changes_view.choose_output_requested.connect(self._choose_output)
        return self.changes_view

    def _build_backups_tab(self) -> QWidget:
        self.backups_view = BackupView(backup_dirs=backup_dirs(), parent=self)
        self.backups_view.restore_requested.connect(self._start_restore)
        self.backups_view.folder_open_requested.connect(self._open_backup_folder)
        self.backups_view.refresh()
        return self.backups_view

    def _build_cloud_tab(self) -> QWidget:
        self.cloud_view = CloudView(self.service, backup_dir=backup_dirs()[0], parent=self)
        self.cloud_view.snapshot_ready.connect(self._on_cloud_snapshot_ready)
        self.cloud_view.upload_ready.connect(self._on_cloud_upload_ready)
        self.cloud_view.operation_failed.connect(self._on_cloud_operation_failed)
        self.cloud_view.operation_progress.connect(self._on_cloud_progress)
        self.cloud_view.busy_changed.connect(self._on_cloud_busy)
        return self.cloud_view

    @staticmethod
    def _placeholder(text: str) -> QWidget:
        box = QGroupBox()
        layout = QVBoxLayout(box)
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return box

    def open_local(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть STALKER 2 .sav",
            "",
            "STALKER 2 save (*.sav);;Все файлы (*)",
        )
        if filename:
            self._start_inspect(Path(filename))

    def _start_inspect(self, path: Path) -> None:
        path = Path(path).expanduser()
        if self._inspect_thread is not None and self._inspect_thread.isRunning():
            return

        self._pending_path = path
        self.open_button.setEnabled(False)
        self.status_label.setText(f"Анализ: {path.name}…")
        self.error_label.clear()
        self.error_label.setVisible(False)

        thread = InspectWorker(self.service, path, self)
        thread.completed.connect(self._on_analysis_ready)
        thread.failed.connect(self._on_analysis_failed)
        thread.finished.connect(self._on_inspect_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._inspect_thread = thread
        self._inspect_worker = thread
        thread.start()

    def _on_analysis_ready(self, snapshot: LocalSnapshot) -> None:
        self.snapshot = snapshot
        self._render_snapshot(snapshot)
        self.analysis_ready.emit(snapshot)

    def _on_analysis_failed(self, message: str) -> None:
        filename = self._pending_path.name if self._pending_path else "Сейв"
        self.status_label.setText("Анализ не выполнен; предыдущий корректный snapshot сохранён")
        self.error_label.setText(f"{filename}: {message}")
        self.error_label.setVisible(True)
        self.analysis_failed.emit(message)

    def _on_inspect_thread_finished(self) -> None:
        self.open_button.setEnabled(True)
        self._inspect_thread = None
        self._inspect_worker = None

    def _render_snapshot(self, snapshot: LocalSnapshot) -> None:
        # Keep the render helper safe for direct synthetic/UI tests as well as
        # the signal path, where _on_analysis_ready already assigned it.
        self.snapshot = snapshot
        info = snapshot.info
        self.staged_counts.clear()
        self.staged_money = None
        self.prepared_edit = None
        self.cloud_view.set_prepared(None)
        crc = "OK" if info.crc_ok else "FAIL"
        money = "unknown" if info.money is None else str(info.money)
        source_label = "Steam Cloud" if snapshot.source_kind == "cloud" else "локальный"
        self.source_label.setText(
            f"Сейв: {snapshot.path.name} • {source_label} • {_human_size(len(snapshot.data))} • SHA {info.sha256[:12]}…"
        )
        self.summary_label.setText(
            f"CRC: {crc}    Money: {money}    Inventory: {len(info.inventory)}    "
            f"Grid cells: {info.grid_cell_count}    Orphans: {len(info.orphans)}"
        )
        warnings = " ".join(info.warnings)
        self.support_label.setText(
            "Поддержанные данные: CRC, money, inventory snapshot. "
            "Неизвестные handles остаются read-only."
            + (f" Предупреждения: {warnings}" if warnings else "")
        )
        self._render_money(info)
        self._render_inventory(info)
        self.changes_view.set_staged(info, self.staged_money, self.staged_counts)
        self.changes_view.invalidate_preview("изменений ещё нет")
        self.status_label.setText("Анализ завершён; snapshot готов")
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.edit_actions_enabled = True
        self._update_action_buttons()

    def _render_inventory(self, info: SaveInfo) -> None:
        self.inventory_view.set_items(info.inventory)
        self.inventory_view.set_staged_counts(self.staged_counts)

    def _render_money(self, info: SaveInfo) -> None:
        if info.money is None or info.money_anchor_count != 1:
            self.money_status_label.setText(
                f"Только чтение: wallet anchor найден {info.money_anchor_count} раз(а)"
            )
            self.money_spin.setEnabled(False)
            self.money_stage_button.setEnabled(False)
            self.money_clear_button.setEnabled(False)
            return
        effective = self.staged_money if self.staged_money is not None else info.money
        self.money_status_label.setText(f"{info.money} → {effective}")
        self.money_spin.blockSignals(True)
        self.money_spin.setEnabled(True)
        self.money_spin.setValue(effective)
        self.money_spin.blockSignals(False)
        self.money_stage_button.setEnabled(True)
        self.money_clear_button.setEnabled(self.staged_money is not None)

    def _on_money_value_changed(self, _value: int) -> None:
        if self.snapshot is None or self.snapshot.info.money is None:
            return
        self.money_status_label.setText(
            f"{self.snapshot.info.money} → {self.money_spin.value()}"
        )

    def _stage_money(self) -> None:
        if self.snapshot is None:
            return
        info = self.snapshot.info
        value = self.money_spin.value()
        if info.money is None or info.money_anchor_count != 1:
            self.money_status_label.setText("Только чтение: wallet anchor не подтверждён")
            return
        if not (0 <= value <= 2_000_000_000):
            self.money_status_label.setText("Сумма отклонена: допустим диапазон 0..2000000000")
            return
        self.staged_money = None if value == info.money else value
        self._render_money(info)
        self._render_changes()
        self._invalidate_preview("изменилось staged значение баланса")
        self.status_label.setText(
            f"Staged: money={'нет' if self.staged_money is None else self.staged_money}, "
            f"stacks={len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

    def _clear_money(self) -> None:
        self.staged_money = None
        if self.snapshot is not None:
            self._render_money(self.snapshot.info)
            self._render_changes()
            self._invalidate_preview("staged баланс очищен")
        self.status_label.setText("Staged balance очищен; bytes сейва не изменены")

    def _find_inventory_item(self, handle: int):
        if self.snapshot is None:
            return None
        return next(
            (item for item in self.snapshot.info.inventory if item.handle == int(handle)),
            None,
        )

    def _stage_stack_change(self, handle: int, new_count: int) -> None:
        item = self._find_inventory_item(handle)
        if item is None:
            self.inventory_view.show_editability_message(
                f"Только чтение: handle 0x{int(handle):08X} не найден в текущем snapshot"
            )
            return
        if not (1 <= int(new_count) <= 1_000_000):
            self.inventory_view.show_editability_message(
                "Новое количество отклонено: допустим диапазон 1..1000000"
            )
            return
        if not item.editable_count:
            if item.count <= 1:
                reason = "count=1"
            else:
                reason = f"неподтверждённый kind={item.kind_code}"
            self.inventory_view.show_editability_message(f"Только чтение: {reason}")
            return

        value = int(new_count)
        if value == item.count:
            self.staged_counts.pop(item.handle, None)
        else:
            self.staged_counts[item.handle] = value
        self.inventory_view.set_staged_counts(self.staged_counts)
        self._render_changes()
        self._invalidate_preview("изменилось staged значение stack")
        self.status_label.setText(
            f"Staged: {len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

    def _clear_selected_stack(self, handle: int) -> None:
        self.staged_counts.pop(int(handle), None)
        self.inventory_view.set_staged_counts(self.staged_counts)
        self._render_changes()
        self._invalidate_preview("staged stack очищен")
        self.status_label.setText(
            f"Staged: {len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

    def _clear_all_stacks(self) -> None:
        self.staged_counts.clear()
        self.staged_money = None
        if self.snapshot is not None:
            self._render_money(self.snapshot.info)
        self.inventory_view.set_staged_counts(self.staged_counts)
        self._render_changes()
        self._invalidate_preview("все staged-правки очищены")
        self.status_label.setText("Все staged-правки очищены; bytes сейва не изменены")

    def _render_changes(self) -> None:
        if self.snapshot is None:
            return
        self.changes_view.set_staged(
            self.snapshot.info,
            self.staged_money,
            self.staged_counts,
        )

    def _has_staged_changes(self) -> bool:
        return self.staged_money is not None or bool(self.staged_counts)

    def _update_action_buttons(self) -> None:
        local_busy = self._operation_thread is not None and self._operation_thread.isRunning()
        busy = local_busy or self._cloud_busy
        has_changes = self.edit_actions_enabled and self._has_staged_changes()
        can_preview = has_changes
        can_apply = self.prepared_edit is not None
        self.preview_button.setEnabled(can_preview and not busy)
        self.save_copy_button.setEnabled(can_apply and not busy)
        self.changes_view.set_actions_enabled(
            preview=can_preview,
            apply=can_apply,
            busy=busy,
        )
        self.backups_view.set_busy(busy)
        self.cloud_view.set_external_busy(local_busy if not self._cloud_busy else False)

    def _show_operation_error(self, message: str) -> None:
        self.status_label.setText("Операция не выполнена")
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.changes_view.set_error(message)
        self.backups_view.set_error(message)
        self.cloud_view.set_error(message)
        self.operation_failed.emit(message)

    def _invalidate_preview(self, reason: str) -> None:
        self.prepared_edit = None
        self.changes_view.invalidate_preview(reason)
        self._update_action_buttons()

    def _build_edit_plan(self) -> EditPlan:
        if self.snapshot is None:
            raise SaveError("Сначала проанализируй сейв")
        if not self._has_staged_changes():
            raise SaveError("Нет staged изменений")
        source_kind = self.snapshot.source_kind
        locator = self.snapshot.locator or str(self.snapshot.path)
        if source_kind not in ("local", "cloud"):
            raise SaveError(f"Неизвестный source kind: {source_kind}")
        return EditPlan(
            source=SourceRef(
                kind=source_kind,
                locator=locator,
                sha256=self.snapshot.info.sha256,
            ),
            money=self.staged_money,
            stacks=tuple(sorted(self.staged_counts.items())),
        )

    def _start_preview(self) -> None:
        if (
            (self._operation_thread is not None and self._operation_thread.isRunning())
            or self._cloud_busy
        ):
            return
        try:
            plan = self._build_edit_plan()
        except SaveError as exc:
            self._show_operation_error(str(exc))
            return

        self.prepared_edit = None
        self._operation_kind = "preview"
        self.changes_view.clear_error()
        self.changes_view.set_progress("Запуск preview…")
        self.status_label.setText("Preview: подготовка…")
        worker = OperationWorker(
            self.service,
            mode="preview",
            data=self.snapshot.data if self.snapshot is not None else b"",
            plan=plan,
            parent=self,
        )
        worker.preview_ready.connect(self._on_preview_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_thread = worker
        self._update_action_buttons()
        worker.start()

    def _on_preview_ready(self, prepared: PreparedEdit) -> None:
        try:
            current_plan = self._build_edit_plan()
        except SaveError as exc:
            self._on_operation_failed(str(exc))
            return
        if prepared.plan != current_plan:
            self._on_operation_failed("Staged форма изменилась во время preview; повтори preview")
            return
        self.prepared_edit = prepared
        self.changes_view.set_preview(prepared)
        self.cloud_view.set_prepared(prepared)
        self.status_label.setText("Preview готов; можно выбрать путь и сохранить копию")
        self.preview_ready.emit(prepared)

    def _on_operation_progress(self, message: str) -> None:
        self.status_label.setText(message)
        self.changes_view.set_progress(message)
        self.backups_view.set_progress(message)

    def _on_operation_failed(self, message: str) -> None:
        if "SHA256" in message or "Источник изменился" in message:
            self.prepared_edit = None
            self.changes_view.invalidate_preview("source SHA изменился")
        self._show_operation_error(message)

    def _on_operation_finished(self) -> None:
        self._operation_thread = None
        self._operation_kind = None
        self.changes_view.set_busy(False)
        self.backups_view.set_busy(False)
        self._update_action_buttons()

    def _choose_output(self) -> None:
        path = self.changes_view.choose_output()
        if path is not None:
            self.changes_view.set_destination(path)

    def _choose_and_start_apply(self) -> None:
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview; запись без него запрещена")
            return
        if self.snapshot is not None and self.snapshot.source_kind == "cloud":
            self._start_cloud_upload()
            return
        value = self.changes_view.destination_edit.text().strip()
        if not value:
            path = self.changes_view.choose_output()
            if path is None:
                return
        else:
            path = Path(value)
        self._start_apply(path)

    def _start_apply(self, output_path: Path, backup_dir: Path | None = None) -> None:
        if (
            (self._operation_thread is not None and self._operation_thread.isRunning())
            or self._cloud_busy
        ):
            return
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview; запись без него запрещена")
            return
        if self.snapshot is None:
            self._show_operation_error("Нет текущего snapshot для apply")
            return
        if self.snapshot.source_kind == "cloud":
            self._start_cloud_upload()
            return
        try:
            current_plan = self._build_edit_plan()
        except SaveError as exc:
            self._show_operation_error(str(exc))
            return
        if self.prepared_edit.plan != current_plan:
            self._invalidate_preview("staged форма изменилась после preview")
            self._show_operation_error("Preview устарел после изменения формы; создай его заново")
            return

        source_path = Path(self.snapshot.path)
        output_path = Path(output_path).expanduser()
        backup_path = Path(backup_dir).expanduser() if backup_dir is not None else backup_dirs()[0]
        worker = OperationWorker(
            self.service,
            mode="apply",
            data=self.snapshot.data,
            plan=self.prepared_edit.plan,
            source_path=source_path,
            output_path=output_path,
            backup_dir=backup_path,
            parent=self,
        )
        worker.set_prepared(self.prepared_edit)
        worker.preview_ready.connect(self._on_preview_ready)
        worker.apply_ready.connect(self._on_apply_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_kind = "apply"
        self._operation_thread = worker
        self.changes_view.set_destination(output_path)
        self.changes_view.set_progress("Запуск local export…")
        self.status_label.setText("Сохранение копии…")
        self._update_action_buttons()
        worker.start()

    def _on_apply_ready(self, receipt) -> None:
        self.prepared_edit = None
        self.changes_view.mark_applied(receipt)
        self.status_label.setText(f"Копия сохранена: {receipt.output_path}")
        self.apply_ready.emit(receipt)

    def _start_restore(self, record, output_path: Path) -> None:
        if self._operation_thread is not None and self._operation_thread.isRunning():
            return
        if getattr(record, "status", None) != "verified":
            self._show_operation_error("Выбранный backup не прошёл проверку SHA256")
            return
        worker = RestoreWorker(self.service, record, Path(output_path), parent=self)
        worker.completed.connect(self._on_restore_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_kind = "restore"
        self._operation_thread = worker
        self.backups_view.set_progress("Запуск restore…")
        self.status_label.setText("Восстановление копии…")
        self._update_action_buttons()
        worker.start()

    def _on_restore_ready(self, receipt) -> None:
        self.backups_view.mark_restored(receipt)
        self.status_label.setText(f"Копия восстановлена: {receipt.output_path}")
        self.restore_ready.emit(receipt)

    def _on_cloud_snapshot_ready(self, snapshot: CloudSnapshot) -> None:
        local_snapshot = LocalSnapshot(
            path=Path(snapshot.name),
            data=snapshot.data,
            info=snapshot.info,
            source_kind="cloud",
            locator=snapshot.name,
        )
        self._render_snapshot(local_snapshot)
        self.analysis_ready.emit(local_snapshot)
        self.status_label.setText(
            f"Cloud snapshot готов: {snapshot.name}; выбери изменения и создай preview"
        )

    def _start_cloud_upload(self) -> None:
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview cloud-сейва")
            return
        self.status_label.setText("Cloud upload: подготовка…")
        self.cloud_view.start_upload()

    def _on_cloud_upload_ready(self, receipt) -> None:
        self.prepared_edit = None
        self.status_label.setText(
            "Cloud: verified" if receipt.status == "verified" else "Cloud: uncertain — требуется reconciliation"
        )
        self._update_action_buttons()
        self.apply_ready.emit(receipt)

    def _on_cloud_operation_failed(self, message: str) -> None:
        self._show_operation_error(message)

    def _on_cloud_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_cloud_busy(self, busy: bool) -> None:
        self._cloud_busy = busy
        self._update_action_buttons()

    def _open_backup_folder(self, path: Path) -> None:
        folder = Path(path).expanduser()
        if not folder.is_dir():
            self._show_operation_error(f"Папка backup не существует: {folder}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self._show_operation_error(f"Не удалось открыть папку backup: {folder}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._operation_thread is not None and self._operation_thread.isRunning():
            self.status_label.setText(
                "Операция ещё выполняется; закрой окно после завершения, чтобы не оборвать запись"
            )
            event.ignore()
            return
        if self.cloud_view.is_busy:
            self.status_label.setText(
                "Cloud operation ещё выполняется; закрой окно после завершения"
            )
            event.ignore()
            return
        if self._inspect_thread is not None and self._inspect_thread.isRunning():
            self._inspect_thread.quit()
            self._inspect_thread.wait(1_000)
        self.cloud_view.close_transport()
        event.accept()


__all__ = ["InspectWorker", "LocalSnapshot", "MainWindow"]
