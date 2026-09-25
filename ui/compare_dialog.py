"""Show what changed between the open save and another one (read-only)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.compare import CompareRow
from editor.i18n import tr


class CompareDialog(QDialog):
    def __init__(
        self,
        rows: Sequence[CompareRow],
        before_name: str,
        after_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("compareDialog")
        self.setWindowTitle(tr("Сравнение сохранений"))
        self.resize(640, 560)
        layout = QVBoxLayout(self)
        intro = QLabel(
            tr("Было: {0}\nСтало: {1}", before_name, after_name)
            if rows
            else tr("Различий в деньгах, предметах и показателях персонажа нет."),
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QTableWidget(len(rows), 3, self)
        self.table.setObjectName("compareTable")
        self.table.setHorizontalHeaderLabels((tr("ПАРАМЕТР"), tr("БЫЛО"), tr("СТАЛО")))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index, row in enumerate(rows):
            for column, value in enumerate((row.label, row.before, row.after)):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self.table.setVisible(bool(rows))
        layout.addWidget(self.table, 1)
        note = QLabel(tr("Предметы сравниваются по типу и общему количеству. Файлы не изменяются."), self)
        note.setWordWrap(True)
        note.setObjectName("settingsHint")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Закрыть"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


__all__ = ["CompareDialog"]
