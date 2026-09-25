"""Verified local/cloud receipt state."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.i18n import tr

from .style_components import action_button, panel, status_chip
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import (
    CLOUD_COPY,
    ERROR_COPY,
    SAVE_SUCCESS,
    format_error_details,
    present_error,
    technical_details,
)


class SaveResultView(QWidget):
    back_to_editor_requested = Signal()
    history_requested = Signal()
    library_requested = Signal()
    reconcile_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("saveResultView")
        self._technical_details = ""
        self._details_dialog: TechnicalDetailsDialog | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        # A receipt is intentionally compact: the dimmed shell remains the
        # context and the verified outcome is the focal card.
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(8)
        heading = QHBoxLayout()
        self.success_icon = QLabel(self)
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "ui" / "shell_icons" / "verified.svg"
        self.success_icon.setPixmap(QIcon(str(icon_path)).pixmap(28, 28))
        self.success_icon.setFixedSize(28, 28)
        heading.addWidget(self.success_icon)
        self.heading_label = QLabel(SAVE_SUCCESS.title, self)
        heading.addWidget(self.heading_label)
        heading.addStretch(1)
        self.status_chip = status_chip(tr("СОХРАНЕНИЕ ПРОВЕРЕНО"), self, tone="success")
        heading.addWidget(self.status_chip)
        root.addLayout(heading)
        self.subtitle = QLabel(SAVE_SUCCESS.message, self)
        self.subtitle.setObjectName("resultSubtitle")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.subtitle)
        receipt_panel = panel(self, object_name="resultReceiptPanel")
        receipt_layout = QVBoxLayout(receipt_panel)
        receipt_layout.setContentsMargins(14, 14, 14, 14)
        self.receipt_table = QTableWidget(0, 2, receipt_panel)
        self.receipt_table.setObjectName("resultReceiptTable")
        self.receipt_table.setHorizontalHeaderLabels((tr("ПРОВЕРКА"), tr("РЕЗУЛЬТАТ")))
        self.receipt_table.verticalHeader().setVisible(False)
        self.receipt_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.receipt_table.setShowGrid(False)
        self.receipt_table.horizontalHeader().setStretchLastSection(True)
        receipt_layout.addWidget(self.receipt_table)
        receipt_panel.setMinimumHeight(150)
        receipt_panel.setMaximumHeight(205)
        root.addWidget(receipt_panel, 0)
        self.reconcile_button = action_button(
            ERROR_COPY["cloud_uncertain"].primary_action,
            self,
            kind="primary",
        )
        self.reconcile_button.setVisible(False)
        self.reconcile_button.clicked.connect(self.reconcile_requested)
        root.addWidget(self.reconcile_button)
        actions = QHBoxLayout()
        self.details_button = action_button(tr("ТЕХНИЧЕСКИЕ ДЕТАЛИ"), self)
        self.details_button.setObjectName("technicalDetailsButton")
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self._show_technical_details)
        actions.addWidget(self.details_button)
        self.editor_button = action_button(SAVE_SUCCESS.primary_action.upper(), self)
        self.editor_button.clicked.connect(self.back_to_editor_requested)
        actions.addWidget(self.editor_button)
        self.history_button = action_button(
            (SAVE_SUCCESS.secondary_action or tr("История")).upper(), self
        )
        self.history_button.clicked.connect(self.history_requested)
        actions.addWidget(self.history_button)
        self.library_button = action_button(tr("ОТКРЫТЬ БИБЛИОТЕКУ"), self)
        self.library_button.clicked.connect(self.library_requested)
        actions.addWidget(self.library_button)
        root.addLayout(actions)
        root.addStretch(1)
        root.insertStretch(0, 1)

    def set_receipt(
        self,
        receipt,
        *,
        status: str | None = None,
        change_count: int | None = None,
    ) -> None:
        """Render only facts present on the operation receipt.

        Local export and restore receipts prove a read-back SHA, while only a
        ``CloudReceipt`` carries an explicit remote certainty state.  A local
        receipt must therefore never inherit the old default ``VERIFIED`` chip.
        """

        receipt_status = status or getattr(receipt, "status", None)
        is_cloud = hasattr(receipt, "remote_path")
        is_uncertain = receipt_status == "uncertain"
        self.reconcile_button.setVisible(is_cloud and is_uncertain)
        if is_cloud:
            chip_text = tr("STEAM НЕ ПОДТВЕРДИЛ ЗАПИСЬ") if is_uncertain else tr("СОХРАНЕНИЕ ПРОВЕРЕНО")
            chip_tone = "warning" if is_uncertain else "success"
            heading = (
                ERROR_COPY["cloud_uncertain"].title
                if is_uncertain
                else SAVE_SUCCESS.title
            )
            subtitle = (
                CLOUD_COPY["uncertain"]
                if is_uncertain
                else CLOUD_COPY["uploaded"]
            )
        elif hasattr(receipt, "safety_backup_path"):
            chip_text = tr("ВОССТАНОВЛЕНО")
            chip_tone = "success"
            heading = tr("ВОССТАНОВЛЕНИЕ ЗАВЕРШЕНО")
            subtitle = tr("Резервная копия восстановлена и проверена.")
        else:
            chip_text = tr("СОХРАНЕНИЕ ПРОВЕРЕНО")
            chip_tone = "success"
            heading = SAVE_SUCCESS.title
            subtitle = SAVE_SUCCESS.message
        self.heading_label.setText(heading)
        self.editor_button.setEnabled(not is_uncertain)
        self.status_chip.setText(chip_text)
        self.status_chip.setProperty("tone", chip_tone)
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)
        rows: list[tuple[str, str]] = []
        detail_lines: list[str] = []
        output_path = getattr(receipt, "output_path", None)
        remote_path = getattr(receipt, "remote_path", None)
        if output_path is not None:
            full_path = str(output_path)
            detail_lines.append(tr("Путь сохранения: {0}", full_path))
        if remote_path is not None:
            full_remote_path = str(remote_path)
            detail_lines.append(tr("Путь Steam Cloud: {0}", full_remote_path))
        for name, attribute in (
            (tr("Резервная копия"), "backup_path"),
            (tr("Файл восстановления"), "recovery_path"),
            (tr("Защитная копия"), "safety_backup_path"),
            (tr("Техническая причина"), "reason"),
        ):
            value = getattr(receipt, attribute, None)
            if value is not None:
                full_value = str(value)
                detail_lines.append(f"{name}: {full_value}")
        digest = getattr(receipt, "output_sha256", None)
        if digest:
            detail_lines.append(tr("SHA-256 результата: {0}", digest))
        if is_cloud:
            detail_lines.append(tr("Статус Steam Cloud: {0}", receipt_status))
            detail_lines.append(
                tr("Steam подтвердил запись: {0}", getattr(receipt, 'persisted', None))
            )
        if is_uncertain:
            rows.append((tr("Состояние"), tr("Steam не подтвердил запись")))
        elif hasattr(receipt, "safety_backup_path"):
            rows.extend(((tr("Восстановление"), tr("Завершено")), (tr("Проверка"), tr("Успешно"))))
        else:
            if change_count is not None:
                remainder = change_count % 100
                if 11 <= remainder <= 14:
                    noun = tr("параметров")
                elif change_count % 10 == 1:
                    noun = tr("параметр")
                elif 2 <= change_count % 10 <= 4:
                    noun = tr("параметра")
                else:
                    noun = tr("параметров")
                rows.append((tr("Изменено"), f"{change_count} {noun}"))
            if getattr(receipt, "backup_path", None) is not None:
                rows.append((tr("Резервная копия"), tr("Создана")))
            rows.append((tr("Проверка"), tr("Успешно")))
        self.receipt_table.setRowCount(len(rows))
        for row, (name, display_value) in enumerate(rows):
            self.receipt_table.setItem(row, 0, QTableWidgetItem(str(name)))
            self.receipt_table.setItem(row, 1, QTableWidgetItem(display_value))
        if detail_lines:
            if is_uncertain:
                detail_presentation = present_error(
                    "cloud_uncertain", "\n".join(detail_lines)
                )
                self._technical_details = format_error_details(detail_presentation)
            else:
                self._technical_details = technical_details("\n".join(detail_lines))
        else:
            self._technical_details = ""
        self.details_button.setVisible(bool(self._technical_details))
        self.subtitle.setText(subtitle)

    def _show_technical_details(self) -> None:
        if not self._technical_details:
            return
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(self._technical_details, self)
        self._details_dialog.open()

    def set_editor_ready(self, ready: bool, message: str | None = None) -> None:
        """Gate the return-to-editor action on verified post-write state."""

        self.editor_button.setEnabled(ready)
        if not ready:
            self.editor_button.setToolTip(message or tr("Ожидается проверка записанного состояния"))
        else:
            self.editor_button.setToolTip("")
        if message:
            self.subtitle.setText(message)
            self.subtitle.setToolTip("")


__all__ = ["SaveResultView"]
