"""Explicit no-writer state for unsupported or ambiguous save releases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .style_components import action_button, panel, status_chip
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import ERROR_COPY, technical_details


class UnsupportedView(QWidget):
    back_requested = Signal()
    diagnostics_requested = Signal()
    folder_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("unsupportedView")
        self._technical_detail_text = ""
        self._details_dialog: TechnicalDetailsDialog | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(QLabel(ERROR_COPY["unsupported"].title, self))
        heading.addStretch(1)
        heading.addWidget(status_chip("ТОЛЬКО ПРОСМОТР", self, tone="warning"))
        root.addLayout(heading)
        self.writer_label = QLabel(ERROR_COPY["unsupported"].message, self)
        self.writer_label.setObjectName("unsupportedWriterLabel")
        self.writer_label.setWordWrap(True)
        root.addWidget(self.writer_label)
        self.detail_panel = panel(self, object_name="unsupportedDetailPanel")
        detail = QVBoxLayout(self.detail_panel)
        detail.setContentsMargins(16, 16, 16, 16)
        self.preview_image = QLabel(self.detail_panel)
        self.preview_image.setObjectName("unsupportedPreviewImage")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview = QPixmap(str(Path(__file__).resolve().parents[1] / "assets" / "ui" / "s2_shell" / "preview_zone.png"))
        if not preview.isNull():
            self.preview_image.setPixmap(preview.scaled(270, 170, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        detail.addWidget(self.preview_image, 0, Qt.AlignmentFlag.AlignLeft)
        self.file_label = QLabel("Файл не выбран", self.detail_panel)
        self.file_label.setObjectName("unsupportedFileLabel")
        self.file_label.setWordWrap(True)
        detail.addWidget(self.file_label)
        self.reason_label = QLabel(
            "Файл можно проверить и просмотреть. Изменения пока недоступны.",
            self.detail_panel,
        )
        self.reason_label.setWordWrap(True)
        detail.addWidget(self.reason_label)
        detail.addStretch(1)
        self.detail_panel.setMinimumHeight(230)
        self.detail_panel.setMaximumHeight(280)
        root.addWidget(self.detail_panel, 0)
        actions = QHBoxLayout()
        self.folder_button = action_button("ОТКРЫТЬ ПАПКУ СОХРАНЕНИЯ", self)
        self.folder_button.clicked.connect(self.folder_requested)
        actions.addWidget(self.folder_button)
        self.diagnostics_button = action_button("СКОПИРОВАТЬ ДИАГНОСТИКУ", self)
        self.diagnostics_button.clicked.connect(self.diagnostics_requested)
        actions.addWidget(self.diagnostics_button)
        self.details_button = action_button("ТЕХНИЧЕСКИЕ ДЕТАЛИ", self)
        self.details_button.setObjectName("unsupportedTechnicalDetailsButton")
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self._show_technical_details)
        actions.addWidget(self.details_button)
        actions.addStretch(1)
        self.back_button = action_button(
            ERROR_COPY["unsupported"].primary_action.upper(), self, kind="primary"
        )
        self.back_button.clicked.connect(self.back_requested)
        actions.addWidget(self.back_button)
        root.addLayout(actions)
        root.addStretch(1)
        root.insertStretch(0, 1)

    def set_snapshot(self, snapshot: Any, reason: str | None = None) -> None:
        self.file_label.setText(
            f"{snapshot.path.name}\n"
            f"Формат: {getattr(snapshot, 'format_title', None) or 'Неизвестный формат'}"
        )
        self.file_label.setToolTip("")
        self.reason_label.setText(ERROR_COPY["unsupported"].message)
        self.reason_label.setToolTip("")
        self._technical_detail_text = technical_details(
            f"Идентификатор формата: {getattr(snapshot, 'format_id', None)}\n"
            f"SHA-256: {snapshot.info.sha256}\n"
            f"Файл: {snapshot.path}\n"
            f"Причина: {reason or 'Редактирование для этой версии ещё не поддерживается.'}"
        )
        self.details_button.setVisible(bool(self._technical_detail_text))

    def _show_technical_details(self) -> None:
        if not self._technical_detail_text:
            return
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(self._technical_detail_text, self)
        self._details_dialog.open()


__all__ = ["UnsupportedView"]
