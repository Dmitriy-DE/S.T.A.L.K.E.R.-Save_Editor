"""Small responsive Qt shell for local save inspection.

The window deliberately owns no parser or writer rules.  It asks
``EditorService`` to inspect bytes in a worker thread and keeps the last valid
snapshot visible when a later file is malformed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from editor.service import EditorService
from save_format import SaveInfo


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


@dataclass(frozen=True)
class LocalSnapshot:
    """Immutable bytes plus inspection result published to the UI thread."""

    path: Path
    data: bytes
    info: SaveInfo


class InspectWorker(QThread):
    """Run one local read/inspect operation outside the UI thread."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, service: EditorService, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.path = path

    def run(self) -> None:
        try:
            data = self.path.read_bytes()
            info = self.service.inspect(data, with_inventory=True)
            self.completed.emit(LocalSnapshot(path=self.path, data=data, info=info))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    """Qt shell for local analysis; editing tabs remain explicit placeholders."""

    analysis_ready = Signal(object)
    analysis_failed = Signal(str)

    def __init__(self, service: EditorService) -> None:
        super().__init__()
        self.service = service
        self.snapshot: LocalSnapshot | None = None
        self.edit_actions_enabled = False
        self._inspect_thread: QThread | None = None
        self._inspect_worker: InspectWorker | None = None
        self._pending_path: Path | None = None

        self.setWindowTitle("S.T.A.L.K.E.R. 2 — Save Editor")
        self.resize(1100, 760)
        self.setMinimumSize(860, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        source_row = QHBoxLayout()
        self.open_button = QPushButton("Открыть .sav…")
        self.open_button.clicked.connect(self.open_local)
        source_row.addWidget(self.open_button)
        self.source_label = QLabel("Сейв не выбран")
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        source_row.addWidget(self.source_label, 1)
        layout.addLayout(source_row)

        self.status_label = QLabel("Готово к локальному анализу")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #a11;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_overview_tab(), "Обзор")
        self.tabs.addTab(self._build_inventory_tab(), "Инвентарь")
        self.tabs.addTab(self._placeholder("Изменения появятся после общего preview gate (U04)."), "Изменения")
        self.tabs.addTab(self._placeholder("Backup journal и restore flow подключаются в U05."), "Резервные копии")
        layout.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.preview_button = QPushButton("Предпросмотр")
        self.preview_button.setEnabled(False)
        self.preview_button.setToolTip("Будет подключено после U03/U04")
        actions.addWidget(self.preview_button)
        self.save_copy_button = QPushButton("Сохранить копию")
        self.save_copy_button.setEnabled(False)
        self.save_copy_button.setToolTip("Будет подключено после U03/U04")
        actions.addWidget(self.save_copy_button)
        layout.addLayout(actions)

        self.setTabOrder(self.open_button, self.tabs)
        self.setTabOrder(self.tabs, self.preview_button)
        self.setTabOrder(self.preview_button, self.save_copy_button)

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.summary_label = QLabel("Открой локальный .sav для проверки CRC и структуры.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Сводка", self.summary_label)
        self.support_label = QLabel("Редактирование отключено до успешного анализа.")
        self.support_label.setWordWrap(True)
        form.addRow("Поддержка", self.support_label)
        return tab

    def _build_inventory_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.inventory_table = QTableWidget(0, 7)
        self.inventory_table.setHorizontalHeaderLabels(
            ["Позиция", "Размер", "Категория", "Type-key", "Кол-во", "Вес", "Handle"]
        )
        self.inventory_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.inventory_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.inventory_table.setAlternatingRowColors(True)
        header = self.inventory_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.inventory_table)
        return tab

    @staticmethod
    def _placeholder(text: str) -> QWidget:
        box = QGroupBox()
        layout = QVBoxLayout(box)
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return box

    def open_local(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть STALKER 2 .sav",
            "",
            "STALKER 2 save (*.sav);;Все файлы (*)",
        )
        if filename:
            self._start_inspect(Path(filename))

    def _start_inspect(self, path: Path) -> None:
        path = Path(path).expanduser()
        if self._inspect_thread is not None and self._inspect_thread.isRunning():
            return

        self._pending_path = path
        self.open_button.setEnabled(False)
        self.status_label.setText(f"Анализ: {path.name}…")
        self.error_label.clear()
        self.error_label.setVisible(False)

        thread = InspectWorker(self.service, path, self)
        thread.completed.connect(self._on_analysis_ready)
        thread.failed.connect(self._on_analysis_failed)
        thread.finished.connect(self._on_inspect_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._inspect_thread = thread
        self._inspect_worker = thread
        thread.start()

    def _on_analysis_ready(self, snapshot: LocalSnapshot) -> None:
        self.snapshot = snapshot
        self._render_snapshot(snapshot)
        self.analysis_ready.emit(snapshot)

    def _on_analysis_failed(self, message: str) -> None:
        filename = self._pending_path.name if self._pending_path else "Сейв"
        self.status_label.setText("Анализ не выполнен; предыдущий корректный snapshot сохранён")
        self.error_label.setText(f"{filename}: {message}")
        self.error_label.setVisible(True)
        self.analysis_failed.emit(message)

    def _on_inspect_thread_finished(self) -> None:
        self.open_button.setEnabled(True)
        self._inspect_thread = None
        self._inspect_worker = None

    def _render_snapshot(self, snapshot: LocalSnapshot) -> None:
        info = snapshot.info
        crc = "OK" if info.crc_ok else "FAIL"
        money = "unknown" if info.money is None else str(info.money)
        self.source_label.setText(
            f"Сейв: {snapshot.path.name} • локальный • {_human_size(len(snapshot.data))} • SHA {info.sha256[:12]}…"
        )
        self.summary_label.setText(
            f"CRC: {crc}    Money: {money}    Inventory: {len(info.inventory)}    "
            f"Grid cells: {info.grid_cell_count}    Orphans: {len(info.orphans)}"
        )
        warnings = " ".join(info.warnings)
        self.support_label.setText(
            "Поддержанные данные: CRC, money, inventory snapshot. "
            "Неизвестные handles остаются read-only."
            + (f" Предупреждения: {warnings}" if warnings else "")
        )
        self._render_inventory(info)
        self.status_label.setText("Анализ завершён; snapshot готов")
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.edit_actions_enabled = True
        self.preview_button.setEnabled(True)
        self.save_copy_button.setEnabled(True)

    def _render_inventory(self, info: SaveInfo) -> None:
        self.inventory_table.setRowCount(len(info.inventory))
        for row, item in enumerate(info.inventory):
            values = (
                item.position,
                item.size_text,
                item.category,
                item.type_key,
                str(item.count),
                f"{item.total_weight:.3f}",
                item.handle_hex,
            )
            for column, value in enumerate(values):
                self.inventory_table.setItem(row, column, QTableWidgetItem(value))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._inspect_thread is not None and self._inspect_thread.isRunning():
            self._inspect_thread.quit()
            self._inspect_thread.wait(1_000)
        event.accept()


__all__ = ["InspectWorker", "LocalSnapshot", "MainWindow"]
