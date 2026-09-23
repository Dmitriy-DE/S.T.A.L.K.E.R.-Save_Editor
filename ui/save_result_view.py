"""Verified local/cloud receipt state."""

from __future__ import annotations

from PySide6.QtCore import Signal
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("saveResultView")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(120, 70, 120, 50)
        root.setSpacing(12)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("СОХРАНЕНИЕ УСПЕШНО ЗАПИСАНО", self))
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
        root.addWidget(receipt_panel, 1)
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

    def set_receipt(self, receipt, *, status: str = "verified") -> None:
        verified = status == "verified"
        self.status_chip.setText("VERIFIED" if verified else "UNCERTAIN")
        self.status_chip.setProperty("tone", "success" if verified else "warning")
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)
        rows = (
            ("Output", getattr(receipt, "output_path", getattr(receipt, "remote_path", "—"))),
            ("Original backup", getattr(receipt, "backup_path", "—")),
            ("Output SHA-256", getattr(receipt, "output_sha256", "—")),
            ("Recovery", getattr(receipt, "recovery_path", "—")),
        )
        self.receipt_table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            self.receipt_table.setItem(row, 0, QTableWidgetItem(str(name)))
            self.receipt_table.setItem(row, 1, QTableWidgetItem(str(value)))
        if not verified:
            self.subtitle.setText("Write отправлен, но результат не подтверждён. Повторная запись заблокирована.")


__all__ = ["SaveResultView"]
