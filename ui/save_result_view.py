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

from .style_components import action_button, panel, status_chip


class SaveResultView(QWidget):
    back_to_editor_requested = Signal()
    history_requested = Signal()
    library_requested = Signal()
    reconcile_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("saveResultView")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        # A receipt is intentionally compact: the dimmed shell remains the
        # context and the verified outcome is the focal card.
        root.setContentsMargins(250, 72, 250, 50)
        root.setSpacing(12)
        heading = QHBoxLayout()
        self.success_icon = QLabel(self)
        icon_path = Path(__file__).resolve().parents[1] / "assets" / "ui" / "shell_icons" / "verified.svg"
        self.success_icon.setPixmap(QIcon(str(icon_path)).pixmap(28, 28))
        self.success_icon.setFixedSize(28, 28)
        heading.addWidget(self.success_icon)
        self.heading_label = QLabel("ОПЕРАЦИЯ ЗАВЕРШЕНА", self)
        heading.addWidget(self.heading_label)
        heading.addStretch(1)
        self.status_chip = status_chip("VERIFIED", self, tone="success")
        heading.addWidget(self.status_chip)
        root.addLayout(heading)
        self.subtitle = QLabel("Все изменения приняты. Данные сохранены с проверкой целостности.", self)
        self.subtitle.setObjectName("resultSubtitle")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.subtitle)
        receipt_panel = panel(self, object_name="resultReceiptPanel")
        receipt_layout = QVBoxLayout(receipt_panel)
        receipt_layout.setContentsMargins(14, 14, 14, 14)
        self.receipt_table = QTableWidget(0, 2, receipt_panel)
        self.receipt_table.setObjectName("resultReceiptTable")
        self.receipt_table.setHorizontalHeaderLabels(("ПРОВЕРКА", "РЕЗУЛЬТАТ"))
        self.receipt_table.verticalHeader().setVisible(False)
        self.receipt_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.receipt_table.horizontalHeader().setStretchLastSection(True)
        receipt_layout.addWidget(self.receipt_table)
        receipt_panel.setMinimumHeight(245)
        receipt_panel.setMaximumHeight(360)
        root.addWidget(receipt_panel, 0)
        self.reconcile_button = action_button(
            "ОБНОВИТЬ STEAM CLOUD / ПРОВЕРИТЬ СОСТОЯНИЕ",
            self,
            kind="primary",
        )
        self.reconcile_button.setVisible(False)
        self.reconcile_button.clicked.connect(self.reconcile_requested)
        root.addWidget(self.reconcile_button)
        actions = QHBoxLayout()
        self.editor_button = action_button("←  ВЕРНУТЬСЯ К РЕДАКТОРУ", self)
        self.editor_button.clicked.connect(self.back_to_editor_requested)
        actions.addWidget(self.editor_button)
        self.history_button = action_button("ОТКРЫТЬ ИСТОРИЮ", self)
        self.history_button.clicked.connect(self.history_requested)
        actions.addWidget(self.history_button)
        self.library_button = action_button("ОТКРЫТЬ БИБЛИОТЕКУ", self)
        self.library_button.clicked.connect(self.library_requested)
        actions.addWidget(self.library_button)
        root.addLayout(actions)
        root.addStretch(1)
        root.insertStretch(0, 1)

    def set_receipt(self, receipt, *, status: str | None = None) -> None:
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
            chip_text = "UNCERTAIN" if is_uncertain else "VERIFIED"
            chip_tone = "warning" if is_uncertain else "success"
            heading = "ЗАПИСЬ В CLOUD ЗАВЕРШЕНА"
            subtitle = (
                "Write отправлен, но remote read-back не подтверждён. Повторная запись заблокирована."
                if is_uncertain
                else "Cloud read-back SHA совпал; локальные recovery-артефакты сохранены."
            )
        elif hasattr(receipt, "safety_backup_path"):
            chip_text = "ВОССТАНОВЛЕНО"
            chip_tone = "success"
            heading = "ВОССТАНОВЛЕНИЕ ЗАВЕРШЕНО"
            subtitle = "Копия записана и проверена по SHA-256."
        else:
            chip_text = "ПРОВЕРЕНО ПО SHA"
            chip_tone = "success"
            heading = "СОХРАНЕНИЕ УСПЕШНО ЗАПИСАНО"
            subtitle = "Выходной файл прочитан обратно; показаны только факты receipt."
        self.heading_label.setText(heading)
        self.editor_button.setEnabled(not is_uncertain)
        self.status_chip.setText(chip_text)
        self.status_chip.setProperty("tone", chip_tone)
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)
        rows: list[tuple[str, object]] = []
        output_path = getattr(receipt, "output_path", None)
        remote_path = getattr(receipt, "remote_path", None)
        if output_path is not None:
            rows.append(("Output", output_path))
        if remote_path is not None:
            rows.append(("Remote path", remote_path))
        for name, attribute in (
            ("Original backup", "backup_path"),
            ("Output SHA-256", "output_sha256"),
            ("Recovery", "recovery_path"),
            ("Safety backup", "safety_backup_path"),
            ("Reason", "reason"),
        ):
            value = getattr(receipt, attribute, None)
            if value is not None:
                rows.append((name, value))
        self.receipt_table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            self.receipt_table.setItem(row, 0, QTableWidgetItem(str(name)))
            self.receipt_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.subtitle.setText(subtitle)

    def set_editor_ready(self, ready: bool, message: str | None = None) -> None:
        """Gate the return-to-editor action on verified post-write state."""

        self.editor_button.setEnabled(ready)
        if not ready:
            self.editor_button.setToolTip(message or "Ожидается проверка записанного состояния")
        else:
            self.editor_button.setToolTip("")
        if message:
            self.subtitle.setText(message)


__all__ = ["SaveResultView"]
