"""Small local support dialog shared by the desktop editor shell."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SupportDialog(QDialog):
    """Show payment details locally without contacting a payment provider."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("supportDialog")
        self.setWindowTitle("Поддержать проект")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(470)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Поддержать проект")
        title.setObjectName("supportTitle")
        layout.addWidget(title)

        intro = QLabel("Если проект оказался полезен, поддержи его развитие.")
        intro.setObjectName("supportIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._add_payment_row(layout, "PayPal", "breygel.dima@gmail.com")
        self._add_payment_row(
            layout,
            "Binance Pay",
            "434350727",
            prefix="Идентификатор Binance:",
        )
        self._add_payment_row(
            layout,
            "USDT",
            "TF5hpkAmF9vjbpaRpJ5ewpbCC122jED1ds",
            prefix="Сеть: TRON (TRC20)\nАдрес:",
        )

        footer = QHBoxLayout()
        footer.addStretch(1)
        close_button = QPushButton("Закрыть")
        close_button.setObjectName("supportCloseButton")
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        layout.addLayout(footer)

    def _add_payment_row(
        self,
        parent_layout: QVBoxLayout,
        title_text: str,
        value_text: str,
        *,
        prefix: str | None = None,
    ) -> None:
        method = QLabel(title_text)
        method.setObjectName("supportMethod")
        parent_layout.addWidget(method)

        if prefix:
            prefix_label = QLabel(prefix)
            prefix_label.setObjectName("supportDetail")
            parent_layout.addWidget(prefix_label)

        value_row = QHBoxLayout()
        value_row.setSpacing(8)
        value = QLineEdit(value_text)
        value.setObjectName("supportValue")
        value.setReadOnly(True)
        value_row.addWidget(value, 1)

        copy_button = QPushButton("Копировать")
        copy_button.setObjectName("supportCopyButton")
        copy_button.clicked.connect(lambda: self._copy_value(copy_button, value_text))
        value_row.addWidget(copy_button)
        parent_layout.addLayout(value_row)

    @staticmethod
    def _copy_value(button: QPushButton, value: str) -> None:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(value)
        button.setText("Скопировано")
        timer = QTimer(button)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: button.setText("Копировать"))
        timer.start(1200)


__all__ = ["SupportDialog"]
