"""Canonical Steam Cloud screen backed by the existing fail-closed CloudView."""

from __future__ import annotations

import os

from PySide6.QtCore import QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .cloud_view import CloudView
from .style_components import action_button, panel, section_header, status_chip


class CloudLibraryView(QWidget):
    """Reference presentation for cloud slots.

    ``CloudView`` remains the owner of transport lifecycle, provenance checks,
    immutable preview validation, and upload certainty.  This widget only
    mirrors its state and forwards explicit user intent to that backend.
    """

    def __init__(self, backend: CloudView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cloudLibraryView")
        self.backend = backend
        self._auto_started = False
        self._build_ui()
        backend.files_ready.connect(self._on_files_ready)
        backend.snapshot_ready.connect(self._on_snapshot_ready)
        backend.upload_ready.connect(self._on_upload_ready)
        backend.operation_failed.connect(self._on_error)
        backend.operation_progress.connect(self._on_progress)
        backend.busy_changed.connect(self._on_busy)
        self._copy_profiles()
        self._on_files_ready(backend.files)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 20, 0, 0)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("STEAM CLOUD", self))
        subtitle = QLabel("Облачные сохранения и подтверждённая запись", self)
        subtitle.setObjectName("screenSubtitle")
        title_row.addWidget(subtitle)
        title_row.addStretch(1)
        self.status_chip = status_chip("НЕ ПОДКЛЮЧЕНО", self, tone="neutral")
        title_row.addWidget(self.status_chip)
        root.addLayout(title_row)

        controls = panel(self, object_name="cloudControlsPanel")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.addWidget(QLabel("ПРОФИЛЬ", controls))
        self.profile_combo = QComboBox(controls)
        self.profile_combo.setObjectName("cloudProfileCombo")
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        controls_layout.addWidget(self.profile_combo, 1)
        self.refresh_button = action_button("⟳  ОБНОВИТЬ СПИСОК", controls)
        self.refresh_button.clicked.connect(self.backend.start_connect)
        controls_layout.addWidget(self.refresh_button)
        self.web_button = action_button("STEAM WEB", controls)
        self.web_button.clicked.connect(self.backend.start_steam_web)
        controls_layout.addWidget(self.web_button)
        root.addWidget(controls)

        body = QHBoxLayout()
        body.setSpacing(10)
        table_panel = panel(self, object_name="cloudTablePanel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.addWidget(section_header("ОБЛАЧНЫЕ СОХРАНЕНИЯ", "DATA PATH · PERSISTED", table_panel))
        self.save_table = QTableWidget(0, 5, table_panel)
        self.save_table.setObjectName("cloudSaveTable")
        self.save_table.setHorizontalHeaderLabels(("НАЗВАНИЕ", "РАЗМЕР", "ДАТА", "PERSISTED", "ИСТОЧНИК"))
        self.save_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.save_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.save_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.save_table.verticalHeader().setVisible(False)
        self.save_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 4):
            self.save_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.save_table.itemSelectionChanged.connect(self._selection_changed)
        table_layout.addWidget(self.save_table, 1)
        body.addWidget(table_panel, 66)

        self.detail_panel = panel(self, object_name="cloudDetailPanel")
        detail = QVBoxLayout(self.detail_panel)
        detail.setContentsMargins(12, 12, 12, 12)
        detail.addWidget(section_header("ПРОСМОТР СОХРАНЕНИЯ", "ИСТОЧНИК И СТАТУС", self.detail_panel))
        self.detail_name = QLabel("Сохранение не выбрано", self.detail_panel)
        self.detail_name.setObjectName("cloudDetailName")
        self.detail_name.setWordWrap(True)
        detail.addWidget(self.detail_name)
        self.detail_meta = QLabel("Выбери Data path, чтобы увидеть детали.", self.detail_panel)
        self.detail_meta.setObjectName("cloudDetailMeta")
        self.detail_meta.setWordWrap(True)
        detail.addWidget(self.detail_meta)
        self.read_only_banner = QLabel(
            "Только чтение до подтверждения Cloud writer. WriteFile не запускается автоматически.",
            self.detail_panel,
        )
        self.read_only_banner.setObjectName("cloudReadOnlyBanner")
        self.read_only_banner.setWordWrap(True)
        detail.addWidget(self.read_only_banner)
        detail.addStretch(1)
        self.download_button = action_button("СКАЧАТЬ И ОТКРЫТЬ", self.detail_panel, kind="primary")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._analyze_selected)
        detail.addWidget(self.download_button)
        self.upload_button = action_button("ЗАПИСАТЬ В CLOUD", self.detail_panel, kind="primary")
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.backend.start_upload)
        detail.addWidget(self.upload_button)
        self.result_label = QLabel("", self.detail_panel)
        self.result_label.setObjectName("cloudResultLabel")
        self.result_label.setWordWrap(True)
        detail.addWidget(self.result_label)
        body.addWidget(self.detail_panel, 34)
        root.addLayout(body, 1)

        safety = panel(self, object_name="cloudSafetyPanel")
        safety_layout = QHBoxLayout(safety)
        safety_layout.setContentsMargins(12, 8, 12, 8)
        safety_layout.addWidget(QLabel("⚠  Cloud запись проходит через backup, fresh read и read-back SHA. При uncertain write повтор запрещён.", safety))
        root.addWidget(safety)

    def _copy_profiles(self) -> None:
        source = self.backend.profile_combo
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for index in range(source.count()):
            self.profile_combo.addItem(source.itemText(index), source.itemData(index))
        self.profile_combo.setCurrentIndex(source.currentIndex())
        self.profile_combo.blockSignals(False)

    def _profile_changed(self, index: int) -> None:
        if index < 0:
            return
        self.backend.profile_combo.setCurrentIndex(index)
        self._on_files_ready(self.backend.files)

    def _selection_changed(self) -> None:
        row = self.save_table.currentRow()
        if 0 <= row < self.backend.table.rowCount():
            self.backend.table.selectRow(row)
        selected = self.save_table.selectedItems()
        self.download_button.setEnabled(bool(selected) and self.backend.transport is not None and not self.backend.is_busy)
        self.upload_button.setEnabled(False)
        if selected:
            self.detail_name.setText(selected[0].text())
            self.detail_meta.setText("Выбран cloud slot. Анализ скачает bytes и проверит формат до редактирования.")

    def _analyze_selected(self) -> None:
        self.backend.analyze_selected()

    def _on_files_ready(self, files) -> None:
        files = tuple(files or ())
        self.save_table.setRowCount(0)
        for row, cloud_file in enumerate(files):
            self.save_table.insertRow(row)
            values = (
                cloud_file.name,
                f"{cloud_file.size} B",
                str(cloud_file.timestamp),
                "да" if cloud_file.is_persisted else "нет",
                str(cloud_file.source),
            )
            for column, value in enumerate(values):
                self.save_table.setItem(row, column, QTableWidgetItem(value))
        self.status_chip.setText("ПОДКЛЮЧЕНО" if files else "СПИСОК ПУСТ")
        self._selection_changed()

    def _on_snapshot_ready(self, snapshot) -> None:
        self.result_label.setText(
            f"Проверено: CRC {'PASS' if snapshot.info.crc_ok else 'FAIL'} · SHA {snapshot.info.sha256[:16]}…"
        )
        self.detail_meta.setText(f"{snapshot.name}\nСнимок скачан; staged изменения ещё не созданы.")
        self.status_chip.setText("СНИМОК ПРОВЕРЕН")

    def _on_upload_ready(self, receipt) -> None:
        self.upload_button.setEnabled(False)
        self.result_label.setText(
            "Cloud verified: persisted=true и read-back SHA совпали."
            if receipt.status == "verified"
            else "Cloud uncertain: повторная запись запрещена до reconciliation."
        )
        self.status_chip.setText("VERIFIED" if receipt.status == "verified" else "UNCERTAIN")

    def _on_error(self, message: str) -> None:
        self.status_chip.setText("ОШИБКА")
        self.result_label.setText(message)

    def _on_progress(self, message: str) -> None:
        self.result_label.setText(message)

    def _on_busy(self, busy: bool) -> None:
        self.refresh_button.setEnabled(not busy)
        self.web_button.setEnabled(not busy)
        self.profile_combo.setEnabled(not busy)
        self.save_table.setEnabled(not busy)
        if busy:
            self.download_button.setEnabled(False)

    def set_prepared(self, prepared) -> None:
        self.backend.set_prepared(prepared)
        self.upload_button.setEnabled(bool(prepared) and self.backend.upload_button.isEnabled())

    def set_catalog_roots(self, roots) -> None:
        self.backend.set_catalog_roots(roots)

    def set_external_busy(self, busy: bool) -> None:
        self.backend.set_external_busy(busy)
        if busy:
            self.download_button.setEnabled(False)

    def set_error(self, message: str) -> None:
        self.backend.set_error(message)
        self._on_error(message)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if self._auto_started or "PYTEST_CURRENT_TEST" in os.environ:
            return
        self._auto_started = True
        QTimer.singleShot(0, self.backend.start_connect)


__all__ = ["CloudLibraryView"]
