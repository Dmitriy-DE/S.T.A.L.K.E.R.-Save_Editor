"""Canonical backup-history surface backed by ``BackupView``."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
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

from .backups_view import BackupView
from .style_components import action_button, panel, section_header, status_chip


class HistoryView(QWidget):
    """Journal presentation; restore remains disabled until backend verification."""

    def __init__(self, backend: BackupView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("historyView")
        self.backend = backend
        self._build_ui()
        self._render()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 20, 0, 0)
        root.setSpacing(10)
        title = QHBoxLayout()
        title.addWidget(QLabel("ИСТОРИЯ И РЕЗЕРВНЫЕ КОПИИ", self))
        subtitle = QLabel("Проверенные операции, SHA и безопасное восстановление", self)
        subtitle.setObjectName("screenSubtitle")
        title.addWidget(subtitle)
        title.addStretch(1)
        self.status_chip = status_chip("ЖУРНАЛ ГОТОВ", self, tone="success")
        title.addWidget(self.status_chip)
        root.addLayout(title)

        body = QHBoxLayout()
        body.setSpacing(10)
        table_panel = panel(self, object_name="historyTablePanel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.addWidget(section_header("ИСТОРИЯ И РЕЗЕРВНЫЕ КОПИИ", "SHA / СТАТУС", table_panel))
        self.table = QTableWidget(0, 5, table_panel)
        self.table.setObjectName("historyTable")
        self.table.setHorizontalHeaderLabels(("ДАТА", "НАЗВАНИЕ СОХРАНЕНИЯ", "ОПЕРАЦИЯ", "SHA", "СТАТУС"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        table_layout.addWidget(self.table, 1)
        toolbar = QHBoxLayout()
        self.refresh_button = action_button("⟳  ОБНОВИТЬ", table_panel)
        self.refresh_button.clicked.connect(self._refresh)
        toolbar.addWidget(self.refresh_button)
        self.open_folder_button = action_button("ОТКРЫТЬ ПАПКУ", table_panel)
        self.open_folder_button.clicked.connect(self.backend._open_folder)
        toolbar.addWidget(self.open_folder_button)
        toolbar.addStretch(1)
        table_layout.addLayout(toolbar)
        body.addWidget(table_panel, 67)

        self.detail_panel = panel(self, object_name="historyDetailPanel")
        detail = QVBoxLayout(self.detail_panel)
        detail.setContentsMargins(12, 12, 12, 12)
        detail.addWidget(section_header("ДЕТАЛИ ЗАПИСИ", "ВОССТАНОВЛЕНИЕ", self.detail_panel))
        self.detail_name = QLabel("Запись не выбрана", self.detail_panel)
        self.detail_name.setObjectName("historyDetailName")
        self.detail_name.setWordWrap(True)
        detail.addWidget(self.detail_name)
        self.detail_status = QLabel("Проверка SHA обязательна перед восстановлением.", self.detail_panel)
        self.detail_status.setObjectName("historyDetailStatus")
        self.detail_status.setWordWrap(True)
        detail.addWidget(self.detail_status)
        self.destination_edit = QLineEdit(self.detail_panel)
        self.destination_edit.setPlaceholderText("Путь восстановленной копии")
        self.destination_edit.textChanged.connect(self._destination_changed)
        detail.addWidget(self.destination_edit)
        detail.addStretch(1)
        self.preview_button = action_button("ПРОВЕРИТЬ BACKUP", self.detail_panel)
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self._preview)
        detail.addWidget(self.preview_button)
        self.restore_button = action_button("ВОССТАНОВИТЬ КОПИЮ", self.detail_panel, kind="primary")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._restore)
        detail.addWidget(self.restore_button)
        self.restore_in_place_button = action_button("ОТКАТИТЬ ИСХОДНЫЙ СЛОТ", self.detail_panel, kind="danger")
        self.restore_in_place_button.setEnabled(False)
        self.restore_in_place_button.clicked.connect(self._restore_in_place)
        detail.addWidget(self.restore_in_place_button)
        body.addWidget(self.detail_panel, 33)
        root.addLayout(body, 1)

    def _refresh(self) -> None:
        self.backend.refresh()
        self._render()

    def _render(self) -> None:
        records = self.backend.records
        with QSignalBlocker(self.table):
            self.table.setRowCount(0)
            for row, record in enumerate(records):
                self.table.insertRow(row)
                values = (
                    record.created_at or "—",
                    record.source_path or "Неизвестный источник",
                    self.backend._operation_text(record.operation),
                    record.source_sha256[:12] + "…" if record.source_sha256 else "—",
                    {"verified": "Проверено", "missing": "Отсутствует", "corrupt": "Повреждено"}.get(record.status, record.status),
                )
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self._selection_changed()

    def _selection_changed(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < self.backend.table.rowCount():
            self.backend.table.selectRow(row)
        record = self.backend.selected_record()
        self.preview_button.setEnabled(record is not None)
        self.restore_button.setEnabled(False)
        self.restore_in_place_button.setEnabled(False)
        if record is None:
            self.detail_name.setText("Запись не выбрана")
            self.detail_status.setText("Проверка SHA обязательна перед восстановлением.")
            return
        self.detail_name.setText(record.source_path or "Неизвестный источник")
        self.detail_status.setText(f"Статус backup: {record.status}. Нажми проверку перед восстановлением.")

    def _preview(self) -> None:
        self.backend.preview_restore()
        self.detail_status.setText(self.backend.preview_label.text())
        self.restore_in_place_button.setEnabled(self.backend.restore_in_place_button.isEnabled())
        self._destination_changed()

    def _destination_changed(self) -> None:
        self.restore_button.setEnabled(
            self.backend._preview_record is not None and bool(self.destination_edit.text().strip())
        )

    def _restore(self) -> None:
        if self.backend._preview_record is None:
            return
        self.backend.destination_edit.setText(self.destination_edit.text())
        self.backend._request_restore()

    def _restore_in_place(self) -> None:
        self.backend._request_restore_in_place()

    def set_busy(self, busy: bool) -> None:
        self.backend.set_busy(busy)
        for widget in (self.refresh_button, self.open_folder_button, self.table, self.destination_edit, self.preview_button, self.restore_button, self.restore_in_place_button):
            widget.setEnabled(not busy)

    def set_progress(self, message: str) -> None:
        self.detail_status.setText(message)

    def set_error(self, message: str) -> None:
        self.detail_status.setText(message)
        self.status_chip.setText("ОШИБКА")

    def mark_restored(self, receipt) -> None:
        self.backend.mark_restored(receipt)
        self._render()
        self.detail_status.setText(self.backend.preview_label.text())

    def mark_in_place_restored(self, receipt) -> None:
        self.backend.mark_in_place_restored(receipt)
        self._render()
        self.detail_status.setText(self.backend.preview_label.text())


__all__ = ["HistoryView"]
