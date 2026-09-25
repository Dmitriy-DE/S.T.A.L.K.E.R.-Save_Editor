"""Canonical backup-history surface backed by the backup controller."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.i18n import tr
from editor.storage import BackupRecord

from .backup_controller import BackupController
from .formatting import human_datetime, source_display_name
from .style_components import action_button, panel, reference_game_rail, section_header, status_chip
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import BACKUP_STATUS_COPY, technical_details

_SHELL_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "s2_shell"


class HistoryView(QWidget):
    """Backup history presentation; restore remains gated on verification."""

    restore_requested = Signal(object, object)
    restore_in_place_requested = Signal(object)
    folder_open_requested = Signal(object)

    def __init__(self, backend: BackupController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("historyView")
        self.backend = backend
        self._visible_records: tuple[BackupRecord, ...] = ()
        self._source_filter = ""
        self._technical_error_details = ""
        self._details_dialog: TechnicalDetailsDialog | None = None
        self._build_ui()
        backend.records_changed.connect(lambda _records: self._render())
        backend.progress_changed.connect(self.set_progress)
        backend.error_changed.connect(self.set_error)
        self._render()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 20, 0, 0)
        root.setSpacing(10)
        title = QHBoxLayout()
        title.addWidget(QLabel(tr("ИСТОРИЯ И РЕЗЕРВНЫЕ КОПИИ"), self))
        subtitle = QLabel(tr("Проверенные действия и безопасное восстановление"), self)
        subtitle.setObjectName("screenSubtitle")
        title.addWidget(subtitle)
        title.addStretch(1)
        self.status_chip = status_chip(tr("ИСТОРИЯ ГОТОВА"), self, tone="success")
        title.addWidget(self.status_chip)
        root.addLayout(title)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(
            reference_game_rail(
                self,
                object_name="historyGameRail",
                active_family="all",
            ),
            0,
        )
        workspace = QHBoxLayout()
        workspace.setSpacing(10)
        table_panel = panel(self, object_name="historyTablePanel")
        self.table_panel = table_panel
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.addWidget(section_header(tr("ИСТОРИЯ РЕЗЕРВНЫХ КОПИЙ"), tr("ПРОВЕРКА / СТАТУС"), table_panel))
        self.source_filter_edit = QLineEdit(table_panel)
        self.source_filter_edit.setPlaceholderText(tr("Фильтр по исходному слоту…"))
        self.source_filter_edit.textChanged.connect(self._filter_changed)
        table_layout.addWidget(self.source_filter_edit)
        self.table = QTableWidget(0, 5, table_panel)
        self.table.setObjectName("historyTable")
        self.table.setHorizontalHeaderLabels((tr("ДАТА"), tr("СОХРАНЕНИЕ"), tr("ДЕЙСТВИЕ"), tr("РЕЗЕРВНАЯ КОПИЯ"), tr("СТАТУС")))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 4):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        # The backup file name is long and technical: keep it narrow, elided in
        # the middle, with the full name in the tooltip, so the table never
        # needs a horizontal scrollbar.
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().resizeSection(3, 190)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        table_layout.addWidget(self.table, 1)
        toolbar = QHBoxLayout()
        self.refresh_button = action_button(tr("ОБНОВИТЬ"), table_panel)
        self.refresh_button.clicked.connect(self._refresh)
        toolbar.addWidget(self.refresh_button)
        self.open_folder_button = action_button(tr("ОТКРЫТЬ ПАПКУ"), table_panel)
        self.open_folder_button.clicked.connect(self._open_folder)
        toolbar.addWidget(self.open_folder_button)
        toolbar.addStretch(1)
        table_layout.addLayout(toolbar)
        workspace.addWidget(table_panel, 67)

        self.detail_panel = panel(self, object_name="historyDetailPanel")
        detail = QVBoxLayout(self.detail_panel)
        detail.setContentsMargins(12, 12, 12, 12)
        detail.addWidget(section_header(tr("ДЕТАЛИ ЗАПИСИ"), tr("ВОССТАНОВЛЕНИЕ"), self.detail_panel))
        self.detail_image = QLabel(self.detail_panel)
        self.detail_image.setObjectName("historyDetailImage")
        self.detail_image.setMinimumHeight(112)
        self.detail_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_pixmap = QPixmap(str(_SHELL_ASSETS / "preview_zone.png"))
        if not detail_pixmap.isNull():
            self.detail_image.setPixmap(detail_pixmap)
            self.detail_image.setScaledContents(True)
        detail.addWidget(self.detail_image)
        self.detail_name = QLabel(tr("Запись не выбрана"), self.detail_panel)
        self.detail_name.setObjectName("historyDetailName")
        self.detail_name.setWordWrap(True)
        detail.addWidget(self.detail_name)
        self.detail_status = QLabel(tr("Перед восстановлением копия будет автоматически проверена."), self.detail_panel)
        self.detail_status.setObjectName("historyDetailStatus")
        self.detail_status.setWordWrap(True)
        detail.addWidget(self.detail_status)
        self.destination_edit = QLineEdit(self.detail_panel)
        self.destination_edit.setPlaceholderText(tr("Путь восстановленной копии"))
        self.destination_edit.textChanged.connect(self._destination_changed)
        detail.addWidget(self.destination_edit)
        self.details_button = action_button(tr("ТЕХНИЧЕСКИЕ ДЕТАЛИ"), self.detail_panel)
        self.details_button.setObjectName("historyTechnicalDetailsButton")
        self.details_button.setEnabled(False)
        self.details_button.clicked.connect(self._show_technical_details)
        detail.addWidget(self.details_button)
        detail.addStretch(1)
        self.preview_button = action_button(tr("ПРОВЕРИТЬ КОПИЮ"), self.detail_panel)
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self._preview)
        detail.addWidget(self.preview_button)
        self.restore_button = action_button(tr("ВОССТАНОВИТЬ КОПИЮ"), self.detail_panel, kind="primary")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._restore)
        detail.addWidget(self.restore_button)
        self.restore_in_place_button = action_button(tr("ОТКАТИТЬ ИСХОДНЫЙ СЛОТ"), self.detail_panel, kind="danger")
        self.restore_in_place_button.setEnabled(False)
        self.restore_in_place_button.clicked.connect(self._restore_in_place)
        detail.addWidget(self.restore_in_place_button)
        workspace.addWidget(self.detail_panel, 33)
        workspace_host = QWidget(self)
        workspace_host.setObjectName("historyWorkspace")
        workspace_host.setLayout(workspace)
        body.addWidget(workspace_host, 1)
        root.addLayout(body, 1)

    def _refresh(self) -> None:
        self.backend.refresh()
        self._render()

    def refresh(self) -> None:
        """Refresh the journal through the controller-owned data path."""

        self._refresh()

    def _filter_changed(self, value: str) -> None:
        self._source_filter = value.strip().casefold()
        self._render()

    def _render(self) -> None:
        records = tuple(
            record
            for record in self.backend.records
            if not self._source_filter
            or self._source_filter in record.source_path.casefold()
            or self._source_filter
            in source_display_name(record.source_path, record.backup_path).casefold()
        )
        self._visible_records = records
        with QSignalBlocker(self.table):
            self.table.setRowCount(0)
            for row, record in enumerate(records):
                self.table.insertRow(row)
                values = (
                    human_datetime(record.created_at),
                    source_display_name(record.source_path, record.backup_path),
                    self._operation_label(record.operation),
                    Path(record.backup_path).name,
                    BACKUP_STATUS_COPY.get(record.status, tr("Требует проверки")),
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem("" if column == 4 else str(value))
                    if column == 3:
                        item.setToolTip(str(value))
                    self.table.setItem(row, column, item)
                tone = {
                    "verified": "success",
                    "missing": "warning",
                    "corrupt": "error",
                }.get(record.status, "neutral")
                status = status_chip(values[4], self.table, tone=tone)
                status.setObjectName("historyVerificationChip")
                self.table.setCellWidget(row, 4, status)
                self.table.setRowHeight(row, 58)
        self.status_chip.setText(tr("ИСТОРИЯ ГОТОВА") if records else tr("ИСТОРИЯ ПОКА ПУСТА"))
        self._selection_changed()

    def _selection_changed(self) -> None:
        record = self._selected_record()
        self.backend.clear_preview()
        self.preview_button.setEnabled(record is not None)
        self.restore_button.setEnabled(False)
        self.restore_in_place_button.setEnabled(False)
        if record is None:
            self.detail_name.setText(tr("Запись не выбрана"))
            self.detail_status.setText(tr("Перед восстановлением копия будет автоматически проверена."))
            self.detail_status.setToolTip("")
            self.destination_edit.clear()
            self.details_button.setEnabled(bool(self._technical_error_details))
            return
        self.detail_name.setText(source_display_name(record.source_path, record.backup_path))
        self.detail_name.setToolTip("")
        self.detail_status.setText(BACKUP_STATUS_COPY.get(record.status, tr("Требует проверки")))
        self.detail_status.setToolTip("")
        self.destination_edit.clear()
        self.details_button.setEnabled(True)

    def _show_technical_details(self) -> None:
        record = self._selected_record()
        if record is None and not self._technical_error_details:
            return
        lines: list[str] = []
        if record is not None:
            lines.extend(
                (
                    tr("Путь к сохранению: {0}", record.source_path),
                    tr("Путь к резервной копии: {0}", record.backup_path),
                    tr("Статус: {0}", record.status),
                    tr("Действие: {0}", self.backend._operation_text(record.operation)),
                )
            )
            for name, value in (
                (tr("SHA-256 сохранения"), record.source_sha256),
                (tr("SHA-256 результата"), record.output_sha256),
                (tr("SHA-256 копии при проверке"), record.actual_sha256),
                (tr("Причина"), record.error),
            ):
                if value:
                    lines.append(f"{name}: {value}")
        if self._technical_error_details:
            lines.append(self._technical_error_details)
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(
            "\n".join(lines) if record is None else technical_details("\n".join(lines)),
            self,
        )
        self._details_dialog.open()

    def _preview(self) -> None:
        checked = self.backend.preview_restore(self._selected_record())
        self.detail_status.setText(
            tr("Резервная копия проверена. Её можно восстановить.")
            if checked is not None
            else tr("Не удалось проверить резервную копию.")
        )
        self.detail_status.setToolTip("")
        self.restore_in_place_button.setEnabled(
            checked is not None and self.backend.can_restore_in_place(checked)
        )
        if checked is not None and not self.destination_edit.text().strip():
            self.destination_edit.setText(str(self.backend.default_restore_destination(checked)))
        self._destination_changed()

    def preview_selected(self) -> None:
        """Verify the selected backup; wired to the visible Enter hint."""

        self._preview()

    def _destination_changed(self) -> None:
        destination = self.destination_edit.text().strip()
        self.destination_edit.setToolTip(destination)
        self.restore_button.setEnabled(
            self.backend.preview_record is not None and bool(destination)
        )

    def _restore(self) -> None:
        if self.backend.preview_record is None:
            return
        destination = self.destination_edit.text().strip()
        if destination:
            self.restore_requested.emit(self.backend.preview_record, Path(destination).expanduser())

    def _restore_in_place(self) -> None:
        if self.backend.preview_record is not None:
            self.restore_in_place_requested.emit(self.backend.preview_record)

    def _open_folder(self) -> None:
        self.folder_open_requested.emit(self.backend.folder_for(self._selected_record()))

    def _selected_record(self):
        row = self.table.currentRow()
        return self._visible_records[row] if 0 <= row < len(self._visible_records) else None

    def select_for_source(self, source: Path | str) -> None:
        """Filter and select the best matching verified journal record."""

        source_path = Path(source).expanduser()
        self.source_filter_edit.setText(source_path.name)
        candidates: list[tuple[int, BackupRecord]] = [
            (row, record)
            for row, record in enumerate(self._visible_records)
            if Path(record.source_path).expanduser() == source_path
            or record.source_path == str(source_path)
        ]
        if not candidates:
            return
        row = next(
            (index for index, record in candidates if record.status == "verified"),
            candidates[0][0],
        )
        self.table.selectRow(row)

    def set_busy(self, busy: bool) -> None:
        self.backend.set_busy(busy)
        for widget in (self.refresh_button, self.open_folder_button, self.table, self.destination_edit, self.preview_button, self.restore_button, self.restore_in_place_button):
            widget.setEnabled(not busy)

    def set_progress(self, message: str) -> None:
        value = str(message).casefold()
        if "восстановление" in value:
            display = tr("Восстанавливаем резервную копию…")
        elif "sha" in value or "проверка копии готова" in value:
            display = tr("Резервная копия проверена. Её можно восстановить.")
        elif "восстановлена" in value or "откачен" in value:
            display = tr("Резервная копия восстановлена и проверена.")
        else:
            display = tr("История резервных копий обновлена.")
        self.detail_status.setText(display)
        self.detail_status.setToolTip("")

    def set_error(self, message: str) -> None:
        self.detail_status.setText(tr("Не удалось проверить или восстановить резервную копию."))
        self.detail_status.setToolTip("")
        self._technical_error_details = technical_details(message)
        self.details_button.setEnabled(True)
        self.status_chip.setText(tr("ТРЕБУЕТ ВНИМАНИЯ"))

    def mark_restored(self, receipt) -> None:
        self.backend.mark_restored(receipt)
        self._render()
        self.detail_status.setText(tr("Резервная копия восстановлена и проверена."))
        self.detail_status.setToolTip("")

    def mark_in_place_restored(self, receipt) -> None:
        self.backend.mark_in_place_restored(receipt)
        self._render()
        self.detail_status.setText(tr("Исходное сохранение восстановлено и проверено."))
        self.detail_status.setToolTip("")

    @staticmethod
    def _operation_label(operation: dict[str, object]) -> str:
        mode = str(operation.get("mode", "")).casefold()
        if "restore" in mode or "recover" in mode:
            return tr("Восстановление")
        if "export" in mode or "copy" in mode:
            return tr("Создание копии")
        if any(
            operation.get(name) is not None
            for name in ("money", "stack_count", "durability_count", "relation_count")
        ):
            return tr("Изменение сохранения")
        return tr("Сохранение")


__all__ = ["HistoryView"]
