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

from editor.cloud_capabilities import cloud_write_capability
from editor.i18n import source_text, tr
from editor.releases import release_by_id

from .cloud_controller import CloudController
from .formatting import human_size
from .style_components import (
    action_button,
    panel,
    reference_game_rail,
    section_header,
    select_rail_family,
    status_chip,
)
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import (
    CLOUD_COPY,
    ERROR_COPY,
    ErrorKind,
    classify_operation_error,
    format_error_details,
    present_error,
    technical_details,
)

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
        self._details_dialog: TechnicalDetailsDialog | None = None
        self._technical_detail_text = ""
        self._build_ui()
        backend.files_ready.connect(self._on_files_ready)
        backend.snapshot_ready.connect(self._on_snapshot_ready)
        backend.upload_ready.connect(self._on_upload_ready)
        backend.operation_failed.connect(self._on_error)
        backend.operation_progress.connect(self._on_progress)
        backend.busy_changed.connect(self._on_busy)
        backend.status_changed.connect(self._on_backend_status)
        backend.result_changed.connect(self._on_backend_result)
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
        subtitle = QLabel(tr("Облачные сохранения и проверенная запись"), self)
        subtitle.setObjectName("screenSubtitle")
        title_row.addWidget(subtitle)
        title_row.addStretch(1)
        self.status_chip = status_chip(tr("НЕ ПОДКЛЮЧЕНО"), self, tone="neutral")
        title_row.addWidget(self.status_chip)
        root.addLayout(title_row)

        controls = panel(self, object_name="cloudControlsPanel")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.addWidget(QLabel(tr("ПРОФИЛЬ"), controls))
        self.profile_combo = QComboBox(controls)
        self.profile_combo.setObjectName("cloudProfileCombo")
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        controls_layout.addWidget(self.profile_combo, 1)
        self.refresh_button = action_button(tr("ОБНОВИТЬ СПИСОК"), controls)
        self.refresh_button.clicked.connect(self.backend.start_connect)
        controls_layout.addWidget(self.refresh_button)
        self.web_button = action_button("STEAM WEB", controls)
        self.web_button.clicked.connect(self.backend.start_steam_web)
        controls_layout.addWidget(self.web_button)
        root.addWidget(controls)

        body = QHBoxLayout()
        body.setSpacing(10)
        self.game_rail = reference_game_rail(
            self,
            object_name="cloudGameRail",
            active_family="stalker2",
        )
        body.addWidget(self.game_rail, 0)
        workspace = QHBoxLayout()
        workspace.setSpacing(10)
        table_panel = panel(self, object_name="cloudTablePanel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.addWidget(section_header(tr("ОБЛАЧНЫЕ СОХРАНЕНИЯ"), tr("СОСТОЯНИЕ ЗАПИСИ"), table_panel))
        self.save_table = QTableWidget(0, 5, table_panel)
        self.save_table.setObjectName("cloudSaveTable")
        self.save_table.setHorizontalHeaderLabels((tr("НАЗВАНИЕ"), tr("РАЗМЕР"), tr("ДАТА"), tr("В CLOUD"), tr("ИСТОЧНИК")))
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
                tr("ПРОСМОТР СОХРАНЕНИЯ"),
                tr("ИСТОЧНИК И СТАТУС"),
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
        self.detail_name = QLabel(tr("Сохранение не выбрано"), self.detail_content)
        self.detail_name.setObjectName("cloudDetailName")
        self.detail_name.setWordWrap(True)
        detail_content_layout.addWidget(self.detail_name)
        self.detail_meta = QLabel(tr("Выбери сохранение, чтобы увидеть подробности."), self.detail_content)
        self.detail_meta.setObjectName("cloudDetailMeta")
        self.detail_meta.setWordWrap(True)
        detail_content_layout.addWidget(self.detail_meta)
        self.read_only_banner = QLabel(
            CLOUD_COPY["write_intro"],
            self.detail_content,
        )
        self.read_only_banner.setObjectName("cloudReadOnlyBanner")
        self.read_only_banner.setWordWrap(True)
        detail_content_layout.addWidget(self.read_only_banner)
        detail_content_layout.addStretch(1)
        self.detail_scroll.setWidget(self.detail_content)
        detail.addWidget(self.detail_scroll, 1)
        self.download_button = action_button(tr("СКАЧАТЬ И ОТКРЫТЬ"), self.detail_panel, kind="primary")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._analyze_selected)
        detail.addWidget(self.download_button)
        self.upload_button = action_button(tr("ЗАПИСАТЬ В CLOUD"), self.detail_panel, kind="primary")
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.backend.start_upload)
        detail.addWidget(self.upload_button)
        self.result_label = QLabel("", self.detail_panel)
        self.result_label.setObjectName("cloudResultLabel")
        self.result_label.setWordWrap(True)
        detail.addWidget(self.result_label)
        self.details_button = action_button(tr("ТЕХНИЧЕСКИЕ ДЕТАЛИ"), self.detail_panel)
        self.details_button.setObjectName("cloudTechnicalDetailsButton")
        self.details_button.setEnabled(False)
        self.details_button.clicked.connect(self._show_technical_details)
        detail.addWidget(self.details_button)
        workspace.addWidget(self.detail_panel, 34)
        workspace_host = QWidget(self)
        workspace_host.setObjectName("cloudWorkspace")
        workspace_host.setLayout(workspace)
        body.addWidget(workspace_host, 1)
        root.addLayout(body, 1)

        safety = panel(self, object_name="cloudSafetyPanel")
        safety_layout = QHBoxLayout(safety)
        safety_layout.setContentsMargins(12, 8, 12, 8)
        safety_layout.addWidget(QLabel(
            tr("Перед записью создаётся резервная копия. Если Steam не подтвердил запись, редактор сначала проверит состояние облака."),
            safety,
        ))
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
        self._sync_rail()

    def _profile_changed(self, index: int) -> None:
        if index < 0:
            return
        self.backend.select_profile(str(self.profile_combo.itemData(index)))
        self._sync_rail()
        self._on_files_ready(self.backend.files)

    def _sync_rail(self) -> None:
        release_id = self.profile_combo.currentData()
        try:
            family = release_by_id(str(release_id)).family if release_id else None
        except KeyError:
            family = None
        select_rail_family(self.game_rail, family)

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
            self.detail_name.setToolTip("")
            self.detail_meta.setText(
                CLOUD_COPY["selected"]
            )
            self._set_technical_details(
                technical_details(
                    tr("Путь в Steam Cloud: {0}\nИсточник: {1}\nСохранено в облаке: {2}", selected_file.name, selected_file.source, selected_file.is_persisted)
                )
                if selected_file is not None
                else ""
            )

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
        # Once connected, the "write becomes available after connecting"
        # banner only stays when the backend really refuses writes, and the
        # stale "connecting…" line goes away.
        self.read_only_banner.setVisible(not cloud_write_capability(self.backend.transport).writable)
        self._set_result("")
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
                tr("Сохранено") if cloud_file.is_persisted else tr("Не подтверждено"),
                self._source_label(cloud_file.source),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                self.save_table.setItem(row, column, item)
        self._on_backend_status(self.backend.status_text)
        selected_row = next(
            (row for row, cloud_file in enumerate(files) if cloud_file == selected_file),
            -1,
        )
        if selected_row >= 0:
            self.save_table.selectRow(selected_row)
        else:
            self.detail_name.setText(
                tr("Сохранение не выбрано") if files else tr("Подходящие сохранения не найдены")
            )
            self.detail_name.setToolTip("")
            self.detail_meta.setText(
                tr("Выбери сохранение, чтобы увидеть подробности.")
                if files
                else tr("В выбранном профиле нет доступных сохранений.")
            )
            self._set_technical_details("")
            self._selection_changed()
        self.save_table.blockSignals(False)
        if selected_row >= 0:
            self._selection_changed()

    def _on_snapshot_ready(self, snapshot) -> None:
        self._set_result(
            CLOUD_COPY["checked"] if snapshot.info.crc_ok else tr("Файл не прошёл проверку"),
            f"CRC: {'PASS' if snapshot.info.crc_ok else 'FAIL'}\n"
            f"SHA-256: {snapshot.info.sha256}",
        )
        self.detail_meta.setText(tr("{0}\nСохранение получено из Steam Cloud.", snapshot.name))
        self.status_chip.setText(tr("СОХРАНЕНИЕ ПРОВЕРЕНО") if snapshot.info.crc_ok else tr("ПРОВЕРКА НЕ ПРОЙДЕНА"))

    def _on_upload_ready(self, receipt) -> None:
        self.upload_button.setEnabled(False)
        uncertain = receipt.status != "verified"
        self.result_label.setText(
            CLOUD_COPY["uploaded"] if not uncertain else CLOUD_COPY["uncertain"]
        )
        detail_lines = (
            tr("Статус: {0}\nСохранено Steam: {1}\nSHA-256: {2}", receipt.status, getattr(receipt, 'persisted', None), getattr(receipt, 'output_sha256', ''))
        )
        detail_text = (
            format_error_details(present_error("cloud_uncertain", detail_lines))
            if uncertain
            else technical_details(detail_lines)
        )
        self._set_technical_details(detail_text)
        self.status_chip.setText(
            tr("ЗАПИСЬ ПРОВЕРЕНА") if receipt.status == "verified" else tr("STEAM НЕ ПОДТВЕРДИЛ ЗАПИСЬ")
        )

    def _on_error(self, message: str) -> None:
        if not message:
            return
        kind = classify_operation_error(message)
        if kind == "cloud_write_unavailable":
            copy = ERROR_COPY[kind]
            self.status_chip.setText(tr("ЗАПИСЬ В CLOUD НЕДОСТУПНА"))
        elif kind == "cloud_uncertain":
            copy = ERROR_COPY[kind]
            self.status_chip.setText(tr("STEAM НЕ ПОДТВЕРДИЛ ЗАПИСЬ"))
        elif kind == "cloud_unavailable":
            copy = ERROR_COPY[kind]
            self.status_chip.setText(tr("STEAM CLOUD НЕДОСТУПЕН"))
        else:
            kind = "generic"
            copy = ERROR_COPY[kind]
            self.status_chip.setText(tr("НЕ УДАЛОСЬ ВЫПОЛНИТЬ ДЕЙСТВИЕ"))
        self._set_result(
            CLOUD_COPY["uncertain"] if kind == "cloud_uncertain" else copy.message,
            format_error_details(present_error(kind, message))
        )

    def _on_progress(self, message: str) -> None:
        if message == tr("Действие в Steam Cloud завершено"):
            return
        normalized = source_text(message).casefold()
        if "подключ" in normalized or "connect" in normalized:
            text = tr("Подключение к Steam Cloud…")
        elif "скачив" in normalized or "download" in normalized:
            text = tr("Получение сохранения из Steam Cloud…")
        elif "sha" in normalized or "fresh read" in normalized or "провер" in normalized:
            text = tr("Проверка сохранения в Steam Cloud…")
        elif "запис" in normalized or "upload" in normalized or "writefile" in normalized:
            text = tr("Запись сохранения в Steam Cloud…")
        else:
            text = tr("Выполняется операция Steam Cloud…")
        self._set_result(text, message)

    def _on_backend_status(self, message: str) -> None:
        normalized = source_text(message).casefold()
        if "uncertain" in normalized or "не подтвержд" in normalized or "reconciliation" in normalized:
            label = tr("STEAM НЕ ПОДТВЕРДИЛ ЗАПИСЬ")
        elif "не подключ" in normalized or "not connected" in normalized:
            label = tr("НЕ ПОДКЛЮЧЕНО")
        elif "verified" in normalized or "подключено" in normalized or "доступен" in normalized:
            label = tr("ПОДКЛЮЧЕНО")
        elif "подключ" in normalized or "connect" in normalized:
            label = tr("ПОДКЛЮЧЕНИЕ…")
        elif "недоступ" in normalized or "не включ" in normalized or "ошиб" in normalized:
            label = tr("STEAM CLOUD НЕДОСТУПЕН")
        elif "обновлён" in normalized or "обновлен" in normalized or "cache" in normalized:
            label = tr("СПИСОК ОБНОВЛЁН")
        elif "операц" in normalized or "operation" in normalized or "ожид" in normalized:
            label = tr("ВЫПОЛНЯЕТСЯ ОПЕРАЦИЯ")
        else:
            label = tr("НЕ ПОДКЛЮЧЕНО")
        self.status_chip.setText(label)
        self._set_technical_details(technical_details(message))

    def _on_backend_result(self, message: str) -> None:
        if not message:
            self.result_label.clear()
            self._set_technical_details("")
            return
        normalized = source_text(message).casefold()
        error_kind: ErrorKind | None = None
        if "uncertain" in normalized or "не подтвержд" in normalized:
            error_kind = "cloud_uncertain"
            text = CLOUD_COPY["uncertain"]
        elif any(token in normalized for token in (
            "upload недоступ", "upload отключ", "writer unavailable", "writer недоступ",
            "запись в облако недоступ", "запись в облако отключ",
        )):
            error_kind = "cloud_write_unavailable"
            text = ERROR_COPY[error_kind].message
        elif "проверка cloud готова" in normalized or "проверка облачного сохранения готова" in normalized:
            text = tr("Изменения проверены. Можно сохранить.")
        elif "проверка не относится" in normalized or "проверка относится к другому" in normalized:
            text = tr("Проверь выбранное сохранение и повтори проверку.")
        elif "сначала выбери" in normalized:
            text = tr("Сначала выбери сохранение и проверь его.")
        elif (
            "verified" in normalized
            or "read-back" in normalized
            or "persisted=true" in normalized
            or "запись в облако подтверждена" in normalized
            or "состояние облака подтверждено" in normalized
        ):
            text = CLOUD_COPY["uploaded"]
        elif "sha" in normalized or "crc" in normalized:
            text = CLOUD_COPY["checked"]
        elif "не подключ" in normalized or "не доступ" in normalized:
            error_kind = "cloud_unavailable"
            text = ERROR_COPY[error_kind].message
        else:
            text = tr("Состояние Steam Cloud обновлено.")
        details = (
            format_error_details(present_error(error_kind, message))
            if error_kind is not None
            else technical_details(message)
        )
        self._set_result(text, details)

    def _set_result(self, text: str, details: str = "") -> None:
        self.result_label.setText(text)
        if details.startswith("Технические детали:"):
            self._set_technical_details(details)
        else:
            self._set_technical_details(technical_details(details))

    def _set_technical_details(self, details: str) -> None:
        self._technical_detail_text = details
        self.details_button.setEnabled(bool(details))

    def _show_technical_details(self) -> None:
        if not self._technical_detail_text:
            return
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(self._technical_detail_text, self)
        self._details_dialog.open()

    @staticmethod
    def _source_label(value: object) -> str:
        source = str(value).casefold()
        if source in {"native_remote_storage", "steam_cloud", "cloud"}:
            return "Steam Cloud"
        if source in {"steam_web", "web"}:
            return "Steam Web"
        return tr("Неизвестно")

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
