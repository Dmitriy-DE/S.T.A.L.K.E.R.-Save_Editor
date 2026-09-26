"""Steam achievements of the selected game: view, unlock, clear (SC-3)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.i18n import tr

from .style_components import action_button

Transport = Any


def default_transport(app_id: int) -> Transport:
    from editor.steam_native import SteamNativeSubprocessWorker

    worker = SteamNativeSubprocessWorker()
    worker.start()
    worker.connect(app_id)
    return worker


class _Job(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[], object], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._action = action

    def run(self) -> None:
        try:
            self.done.emit(self._action())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class AchievementsDialog(QDialog):
    def __init__(
        self,
        app_id: int,
        title: str,
        parent: QWidget | None = None,
        *,
        transport_factory: Callable[[int], Transport] = default_transport,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("achievementsDialog")
        self.setWindowTitle(tr("Достижения Steam") + f" — {title}")
        self.resize(820, 620)
        self._app_id = app_id
        self._factory = transport_factory
        self._items: list[dict[str, Any]] = []
        self._job: _Job | None = None

        layout = QVBoxLayout(self)
        self.status = QLabel(tr("Загрузка достижений…"), self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels([tr("Название"), tr("Описание"), tr("Статус")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        self.unlock_button = action_button(tr("Получить"), self, kind="primary")
        self.clear_button = action_button(tr("Сбросить"), self)
        self.close_button = action_button(tr("Закрыть"), self)
        self.unlock_button.clicked.connect(lambda: self._change(True))
        self.clear_button.clicked.connect(lambda: self._change(False))
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.unlock_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self._sync_buttons()
        self._run(self._load, self._loaded)

    # --- background work --------------------------------------------------
    def _run(self, action: Callable[[], object], on_done: Callable[[object], None]) -> None:
        self._set_busy(True)
        job = _Job(action, self)
        job.done.connect(on_done)
        job.failed.connect(self._failed)
        job.finished.connect(lambda: self._set_busy(False))
        self._job = job
        job.start()

    def _load(self) -> object:
        transport = self._factory(self._app_id)
        try:
            return transport.list_achievements()
        finally:
            transport.close()

    def _loaded(self, items: object) -> None:
        self._items = list(items) if isinstance(items, list) else []
        self._render()

    def _failed(self, message: str) -> None:
        self.status.setText(message)

    def _set_busy(self, busy: bool) -> None:
        self.table.setEnabled(not busy)
        self._busy = busy
        self._sync_buttons()

    # --- view ---------------------------------------------------------------
    def _render(self) -> None:
        done = sum(1 for item in self._items if item.get("achieved"))
        self.status.setText(tr("Получено {0} из {1}", done, len(self._items)))
        self.table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            name = str(item.get("name") or item.get("api_name"))
            status = tr("Получено") if item.get("achieved") else tr("Не получено")
            if item.get("achieved") and item.get("unlock_time"):
                status += " · " + datetime.fromtimestamp(int(item["unlock_time"])).strftime("%d.%m.%Y")
            for column, text in enumerate((name, str(item.get("description") or ""), status)):
                cell = QTableWidgetItem(text)
                cell.setToolTip(str(item.get("api_name")))
                self.table.setItem(row, column, cell)
        self._sync_buttons()

    def _selected(self) -> dict[str, Any] | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        row = rows[0].row()
        return self._items[row] if 0 <= row < len(self._items) else None

    def _sync_buttons(self) -> None:
        item = self._selected()
        busy = getattr(self, "_busy", False)
        self.unlock_button.setEnabled(not busy and item is not None and not item.get("achieved"))
        self.clear_button.setEnabled(not busy and item is not None and bool(item.get("achieved")))

    def _change(self, achieved: bool) -> None:
        item = self._selected()
        if item is None:
            return
        name = str(item.get("name") or item.get("api_name"))
        answer = QMessageBox.question(
            self,
            tr("Достижения Steam"),
            tr("Изменить достижение «{0}» в профиле Steam?", name),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        api_name = str(item["api_name"])

        def action() -> object:
            transport = self._factory(self._app_id)
            try:
                transport.set_achievement(api_name, achieved)
                return transport.list_achievements()
            finally:
                transport.close()

        self._run(action, self._loaded)


__all__ = ["AchievementsDialog"]
