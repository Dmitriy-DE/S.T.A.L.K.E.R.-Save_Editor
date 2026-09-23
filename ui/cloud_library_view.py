"""Canonical Steam Cloud screen backed by the fail-closed cloud controller."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .cloud_controller import CloudController
from .formatting import human_size
from .style_components import action_button, panel, reference_game_rail, section_header, status_chip

_SHELL_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "s2_shell"


class CloudLibraryView(QWidget):
    """Reference presentation for cloud slots.

    ``CloudController`` remains the owner of transport lifecycle, provenance checks,
    immutable preview validation, and upload certainty.  This widget only
    mirrors its state and forwards explicit user intent to that backend.
    """

    def __init__(self, backend: CloudController, parent: QWidget | None = None) -> None:
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
        backend.status_changed.connect(self.status_chip.setText)
        backend.result_changed.connect(self.result_label.setText)
        backend.error_changed.connect(self._on_error)
        backend.upload_available_changed.connect(self.upload_button.setEnabled)
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
        self.refresh_button = action_button("ОБНОВИТЬ СПИСОК", controls)
        self.refresh_button.clicked.connect(self.backend.start_connect)
        controls_layout.addWidget(self.refresh_button)
        self.web_button = action_button("STEAM WEB", controls)
        self.web_button.clicked.connect(self.backend.start_steam_web)
        controls_layout.addWidget(self.web_button)
        root.addWidget(controls)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(
            reference_game_rail(
                self,
                object_name="cloudGameRail",
                active_family="stalker2",
            ),
            0,
        )
        workspace = QHBoxLayout()
        workspace.setSpacing(10)
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
        self.save_table.setShowGrid(False)
        self.save_table.verticalHeader().setVisible(False)
        self.save_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 4):
            self.save_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.save_table.itemSelectionChanged.connect(self._selection_changed)
        table_layout.addWidget(self.save_table, 1)
        workspace.addWidget(table_panel, 66)

        self.detail_panel = panel(self, object_name="cloudDetailPanel")
        detail = QVBoxLayout(self.detail_panel)
        detail.setContentsMargins(12, 12, 12, 12)
        self.detail_scroll = QScrollArea(self.detail_panel)
        self.detail_scroll.setObjectName("cloudDetailScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.detail_content = QWidget(self.detail_scroll)
        self.detail_content.setObjectName("cloudDetailContent")
        detail_content_layout = QVBoxLayout(self.detail_content)
        detail_content_layout.setContentsMargins(0, 0, 5, 0)
        detail_content_layout.setSpacing(5)
        detail_content_layout.addWidget(
            section_header(
                "ПРОСМОТР СОХРАНЕНИЯ",
                "ИСТОЧНИК И СТАТУС",
                self.detail_content,
            )
        )
        self.detail_image = QLabel(self.detail_content)
        self.detail_image.setObjectName("cloudDetailImage")
        self.detail_image.setMinimumHeight(118)
        self.detail_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_pixmap = QPixmap(str(_SHELL_ASSETS / "preview_zone.png"))
        if not detail_pixmap.isNull():
            self.detail_image.setPixmap(detail_pixmap)
            self.detail_image.setScaledContents(True)
        detail_content_layout.addWidget(self.detail_image)
        self.detail_name = QLabel("Сохранение не выбрано", self.detail_content)
        self.detail_name.setObjectName("cloudDetailName")
        self.detail_name.setWordWrap(True)
        detail_content_layout.addWidget(self.detail_name)
        self.detail_meta = QLabel("Выбери Data path, чтобы увидеть детали.", self.detail_content)
        self.detail_meta.setObjectName("cloudDetailMeta")
        self.detail_meta.setWordWrap(True)
        detail_content_layout.addWidget(self.detail_meta)
        self.read_only_banner = QLabel(
            "Только чтение до подтверждения Cloud writer. WriteFile не запускается автоматически.",
            self.detail_content,
        )
        self.read_only_banner.setObjectName("cloudReadOnlyBanner")
        self.read_only_banner.setWordWrap(True)
        detail_content_layout.addWidget(self.read_only_banner)
        detail_content_layout.addStretch(1)
        self.detail_scroll.setWidget(self.detail_content)
        detail.addWidget(self.detail_scroll, 1)
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
        workspace.addWidget(self.detail_panel, 34)
        workspace_host = QWidget(self)
        workspace_host.setObjectName("cloudWorkspace")
        workspace_host.setLayout(workspace)
        body.addWidget(workspace_host, 1)
        root.addLayout(body, 1)

        safety = panel(self, object_name="cloudSafetyPanel")
        safety_layout = QHBoxLayout(safety)
        safety_layout.setContentsMargins(12, 8, 12, 8)
        safety_layout.addWidget(QLabel("Cloud запись проходит через backup, fresh read и read-back SHA. При uncertain write повтор запрещён.", safety))
        root.addWidget(safety)

    def _copy_profiles(self) -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        profiles = self.backend.profiles
        for profile in profiles:
            self.profile_combo.addItem(profile.title, profile.release_id)
        current_index = self.profile_combo.findData(self.backend.profile.release_id)
        self.profile_combo.setCurrentIndex(max(0, current_index))
        self.profile_combo.blockSignals(False)

    def _profile_changed(self, index: int) -> None:
        if index < 0:
            return
        self.backend.select_profile(str(self.profile_combo.itemData(index)))
        self._on_files_ready(self.backend.files)

    def _selection_changed(self) -> None:
        row = self.save_table.currentRow()
        selected_file = self.backend.files[row] if 0 <= row < len(self.backend.files) else None
        self.backend.select_file(selected_file)
        selected = self.save_table.selectedItems()
        self.download_button.setEnabled(bool(selected) and self.backend.transport is not None and not self.backend.is_busy)
        self.upload_button.setEnabled(False)
        if selected:
            name = PurePosixPath(selected_file.name.replace("\\", "/")).name if selected_file is not None else selected[0].text()
            self.detail_name.setText(name)
            self.detail_name.setToolTip(selected_file.name if selected_file is not None else "")
            self.detail_meta.setText("Выбран cloud slot. Анализ скачает bytes и проверит формат до редактирования.")

    def _analyze_selected(self) -> None:
        self.backend.analyze_selected()

    def analyze_selected(self) -> None:
        """Analyze the selected cloud row; wired to the visible Enter hint."""

        self._analyze_selected()

    def refresh(self) -> None:
        """Refresh the cloud listing; wired to the visible R hint."""

        self.backend.start_connect()

    def _on_files_ready(self, files) -> None:
        files = tuple(files or ())
        selected_file = self.backend.selected_file()
        self.save_table.blockSignals(True)
        self.save_table.setRowCount(0)
        for row, cloud_file in enumerate(files):
            self.save_table.insertRow(row)
            self.save_table.setRowHeight(row, 58)
            values = (
                PurePosixPath(cloud_file.name.replace("\\", "/")).name,
                human_size(cloud_file.size),
                datetime.fromtimestamp(cloud_file.timestamp).strftime("%d.%m.%Y %H:%M"),
                "да" if cloud_file.is_persisted else "нет",
                "Неизвестно" if str(cloud_file.source) == "unknown" else str(cloud_file.source),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setToolTip(cloud_file.name)
                self.save_table.setItem(row, column, item)
        status = self.backend.status_text
        if status.startswith("Steam Cloud:"):
            status = status.removeprefix("Steam Cloud:").strip()
        self.status_chip.setText(status.upper())
        selected_row = next(
            (row for row, cloud_file in enumerate(files) if cloud_file == selected_file),
            -1,
        )
        if selected_row >= 0:
            self.save_table.selectRow(selected_row)
        else:
            self._selection_changed()
        self.save_table.blockSignals(False)
        if selected_row >= 0:
            self._selection_changed()

    def _on_snapshot_ready(self, snapshot) -> None:
        self.result_label.setText(
            f"Проверено: CRC {'PASS' if snapshot.info.crc_ok else 'FAIL'} · SHA {snapshot.info.sha256[:16]}…"
        )
        self.detail_meta.setText(f"{snapshot.name}\nСнимок скачан; изменения ещё не созданы.")
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
        if not message:
            return
        self.status_chip.setText("ОШИБКА")
        self.result_label.setText(message)

    def _on_progress(self, message: str) -> None:
        if message != "Cloud operation завершена":
            self.result_label.setText(message)

    def _on_busy(self, busy: bool) -> None:
        self.refresh_button.setEnabled(not busy)
        self.web_button.setEnabled(not busy)
        self.profile_combo.setEnabled(not busy)
        self.save_table.setEnabled(not busy)
        if busy:
            self.download_button.setEnabled(False)
        else:
            self._selection_changed()

    def set_prepared(self, prepared) -> None:
        self.backend.set_prepared(prepared)

    def set_catalog_roots(self, roots) -> None:
        self.backend.set_catalog_roots(roots)

    def set_external_busy(self, busy: bool) -> None:
        self.backend.set_external_busy(busy)
        if busy:
            self.download_button.setEnabled(False)

    def set_error(self, message: str) -> None:
        self.backend.set_error(message)
        self._on_error(message)

    def close(self) -> bool:
        """Stop cloud workers before the presentation widget is destroyed."""

        self.backend.close()
        return super().close()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if self._auto_started or "PYTEST_CURRENT_TEST" in os.environ:
            return
        self._auto_started = True
        QTimer.singleShot(0, self.backend.start_connect)


__all__ = ["CloudLibraryView"]
