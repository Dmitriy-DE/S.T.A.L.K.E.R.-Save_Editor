"""Visible confirmation state for the existing immutable preview pipeline."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .style_components import action_button, panel, section_header, status_chip


class SaveReviewView(QWidget):
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("saveReviewView")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        # This is a confirmation card, not a second full-screen editor.  Keep
        # the application context visible around a bounded review surface.
        root.setContentsMargins(42, 24, 42, 24)
        root.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("ПОДТВЕРЖДЕНИЕ СОХРАНЕНИЯ", self))
        heading.addStretch(1)
        self.status_chip = status_chip("ПРОВЕРКА ПЕРЕД СОХРАНЕНИЕМ", self, tone="warning")
        heading.addWidget(self.status_chip)
        root.addLayout(heading)
        self.source_label = QLabel("Изменения ожидают подтверждения.", self)
        self.source_label.setObjectName("reviewSourceLabel")
        self.source_label.setWordWrap(True)
        root.addWidget(self.source_label)

        body = QHBoxLayout()
        body.setSpacing(12)
        changes_panel = panel(self, object_name="reviewChangesPanel")
        changes_layout = QVBoxLayout(changes_panel)
        changes_layout.setContentsMargins(12, 12, 12, 12)
        changes_layout.addWidget(section_header("ПЛАНИРУЕМЫЕ ИЗМЕНЕНИЯ", "ПРОВЕРКА", changes_panel))
        self.changes_table = QTableWidget(0, 3, changes_panel)
        self.changes_table.setObjectName("reviewChangesTable")
        self.changes_table.setHorizontalHeaderLabels(("ОБЪЕКТ", "БЫЛО", "СТАНЕТ"))
        self.changes_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.changes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.changes_table.setShowGrid(False)
        self.changes_table.verticalHeader().setVisible(False)
        changes_layout.addWidget(self.changes_table, 1)
        body.addWidget(changes_panel, 66)

        pipeline_panel = panel(self, object_name="reviewPipelinePanel")
        pipeline_layout = QVBoxLayout(pipeline_panel)
        pipeline_layout.setContentsMargins(12, 12, 12, 12)
        pipeline_layout.addWidget(section_header("ПОРЯДОК СОХРАНЕНИЯ", parent=pipeline_panel))
        self.pipeline_steps = QListWidget(pipeline_panel)
        self.pipeline_steps.setObjectName("reviewPipelineSteps")
        for text in (
            "1  Проверить изменения",
            "2  Создать резервную копию",
            "3  Сохранить файл",
            "4  Проверить результат",
        ):
            self.pipeline_steps.addItem(QListWidgetItem(text))
        pipeline_layout.addWidget(self.pipeline_steps, 1)
        self.warning_label = QLabel(
            "Если Steam не подтвердил запись, редактор сначала проверит состояние облака.",
            pipeline_panel,
        )
        self.warning_label.setObjectName("reviewWarningLabel")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        pipeline_layout.addWidget(self.warning_label)
        body.addWidget(pipeline_panel, 34)
        body_host = QWidget(self)
        body_host.setObjectName("reviewBodyHost")
        body_host.setLayout(body)
        body_host.setMinimumHeight(270)
        body_host.setMaximumHeight(310)
        root.addWidget(body_host, 0)

        actions = QHBoxLayout()
        self.cancel_button = action_button("ОТМЕНА", self)
        self.cancel_button.clicked.connect(self.cancelled)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        self.confirm_button = action_button("СОХРАНИТЬ С ИЗМЕНЕНИЯМИ", self, kind="primary")
        self.confirm_button.clicked.connect(self.confirmed)
        actions.addWidget(self.confirm_button)
        root.addLayout(actions)
        root.addStretch(1)
        root.insertStretch(0, 1)

    def set_source(self, text: str, *, cloud: bool = False) -> None:
        self.source_label.setText(text)
        self.warning_label.setVisible(cloud)

    def set_changes(self, rows: Iterable[tuple[str, str, str]]) -> None:
        rows = tuple(rows)
        self.changes_table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.changes_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.confirm_button.setEnabled(bool(rows))

    def set_busy(self, busy: bool) -> None:
        self.cancel_button.setEnabled(not busy)
        self.confirm_button.setEnabled(not busy and self.changes_table.rowCount() > 0)


__all__ = ["SaveReviewView"]
