"""Small opt-in viewer for diagnostic information."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from editor.i18n import tr


class TechnicalDetailsDialog(QDialog):
    """Show selectable, scrollable diagnostics with an explicit copy action."""

    def __init__(self, details: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("technicalDetailsDialog")
        self.setWindowTitle(tr("Технические детали"))
        self.setModal(True)
        self.setMinimumSize(460, 280)
        self.resize(740, 440)

        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit(self)
        self.text.setObjectName("technicalDetailsText")
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text.setPlainText(str(details))
        layout.addWidget(self.text, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.copy_button = QPushButton(tr("Копировать"), self)
        self.copy_button.setObjectName("copyTechnicalDetailsButton")
        self.copy_button.clicked.connect(self._copy)
        actions.addWidget(self.copy_button)
        self.close_button = QPushButton(tr("Закрыть"), self)
        self.close_button.clicked.connect(self.accept)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.text.toPlainText())
        self.copy_button.setText(tr("Скопировано"))


__all__ = ["TechnicalDetailsDialog"]
