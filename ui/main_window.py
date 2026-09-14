"""Small responsive Qt shell for local save inspection.

The window deliberately owns no parser or writer rules.  It asks
``EditorService`` to inspect bytes in a worker thread and keeps the last valid
snapshot visible when a later file is malformed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from editor.formats import FormatDetectionError
from editor.models import EditPlan, PreparedEdit, SourceRef
from editor.platforms import backup_dirs
from editor.service import EditorService
from save_format import SaveError, SaveInfo

from .backups_view import BackupView, RestoreWorker
from .changes_view import ChangesView
from .cloud_view import CloudSnapshot, CloudView
from .inventory_view import InventoryView
from .operation_worker import OperationWorker
from .theme import apply_theme


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _version_text() -> str:
    """Read the repository version without introducing a packaging dependency."""

    version_path = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        value = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        value = "0.4.0"
    return value or "0.4.0"


@dataclass(frozen=True)
class LocalSnapshot:
    """Immutable bytes plus inspection result published to the UI thread."""

    path: Path
    data: bytes
    info: SaveInfo
    source_kind: str = "local"
    locator: str | None = None
    format_id: str = "stalker2"
    format_title: str = "S.T.A.L.K.E.R. 2: Heart of Chornobyl"


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
            result = self.service.inspect_result(
                data,
                with_inventory=True,
                source_name=self.path.name,
            )
            self.completed.emit(
                LocalSnapshot(
                    path=self.path,
                    data=data,
                    info=result.info,
                    format_id=result.format_id,
                    format_title=result.format_title,
                )
            )
        except FormatDetectionError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    """Qt shell for local analysis, safe edits and local backup restore."""

    analysis_ready = Signal(object)
    analysis_failed = Signal(str)
    preview_ready = Signal(object)
    apply_ready = Signal(object)
    restore_ready = Signal(object)
    operation_failed = Signal(str)

    def __init__(self, service: EditorService) -> None:
        super().__init__()
        self.service = service
        self.snapshot: LocalSnapshot | None = None
        self.staged_counts: dict[int, int] = {}
        self.staged_money: int | None = None
        self.prepared_edit: PreparedEdit | None = None
        self.edit_actions_enabled = False
        self._inspect_thread: QThread | None = None
        self._inspect_worker: InspectWorker | None = None
        self._pending_path: Path | None = None
        self._operation_thread: QThread | None = None
        self._operation_kind: str | None = None
        self._cloud_busy = False

        # QApplication.instance() is typed as the base QCoreApplication.
        application = QApplication.instance()
        apply_theme(application if isinstance(application, QApplication) else None)
        self.setWindowTitle("S.T.A.L.K.E.R. 2 — Save Editor")
        self.resize(1280, 820)
        self.setMinimumSize(960, 620)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_bar = QFrame()
        title_bar.setObjectName("titleBar")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(18, 12, 18, 12)
        title_layout.setSpacing(10)
        self.app_title = QLabel("S.T.A.L.K.E.R. 2 Save Editor")
        self.app_title.setObjectName("appTitle")
        title_layout.addWidget(self.app_title)
        self.version_badge = QLabel(f"v{_version_text()}")
        self.version_badge.setObjectName("versionBadge")
        title_layout.addWidget(self.version_badge)
        title_layout.addStretch(1)
        ui_hint = QLabel("ZONE / SAVE WORKBENCH")
        ui_hint.setObjectName("sidebarStatus")
        title_layout.addWidget(ui_hint)
        layout.addWidget(title_bar)

        meta_bar = QFrame()
        meta_bar.setObjectName("metaBar")
        meta_layout = QHBoxLayout(meta_bar)
        meta_layout.setContentsMargins(18, 9, 18, 9)
        meta_layout.setSpacing(10)
        self.file_source_badge = QLabel("ФАЙЛ НЕ ВЫБРАН")
        self.file_source_badge.setObjectName("sourceBadge")
        meta_layout.addWidget(self.file_source_badge)
        meta_text = QVBoxLayout()
        meta_text.setSpacing(1)
        self.meta_filename = QLabel("Сейв не выбран")
        self.meta_filename.setObjectName("metaFilename")
        meta_text.addWidget(self.meta_filename)
        self.meta_details = QLabel("Открой локальный .sav для проверки CRC и структуры")
        self.meta_details.setObjectName("metaDetails")
        self.meta_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        meta_text.addWidget(self.meta_details)
        meta_layout.addLayout(meta_text, 1)
        self.integrity_badge = QLabel("CRC-32: —")
        self.integrity_badge.setObjectName("integrityBadge")
        meta_layout.addWidget(self.integrity_badge)
        self.format_badge = QLabel("UE5 GVAS: —")
        self.format_badge.setObjectName("formatBadge")
        meta_layout.addWidget(self.format_badge)
        self.open_button = QPushButton("Открыть .sav…")
        self.open_button.setObjectName("openButton")
        self.open_button.clicked.connect(self.open_local)
        meta_layout.addWidget(self.open_button)
        layout.addWidget(meta_bar)

        # Retain the original public label for small integrations and tests;
        # the shell presents the same facts as structured metadata above.
        self.source_label = QLabel("Сейв не выбран")
        self.source_label.setObjectName("sourceLabel")
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_label.setVisible(False)

        self.status_label = QLabel("Готово к локальному анализу")
        self.status_label.setObjectName("statusLabel")
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(18, 8, 18, 8)
        status_layout.addWidget(self.status_label)
        layout.addLayout(status_layout)
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        error_layout = QHBoxLayout()
        error_layout.setContentsMargins(18, 0, 18, 8)
        error_layout.addWidget(self.error_label)
        layout.addLayout(error_layout)

        body = QHBoxLayout()
        body.setContentsMargins(18, 0, 18, 12)
        body.setSpacing(12)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(218)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 12, 10, 10)
        sidebar_layout.setSpacing(5)
        sidebar_heading = QLabel("РАЗДЕЛЫ")
        sidebar_heading.setObjectName("sidebarHeading")
        sidebar_layout.addWidget(sidebar_heading)

        content_panel = QFrame()
        content_panel.setObjectName("contentPanel")
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(12, 8, 12, 10)
        content_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("contentTabs")
        self.tabs.addTab(self._build_overview_tab(), "Обзор")
        self.tabs.addTab(self._build_inventory_tab(), "Инвентарь")
        self.tabs.addTab(self._build_changes_tab(), "Изменения")
        self.tabs.addTab(self._build_backups_tab(), "Резервные копии")
        self.tabs.addTab(self._build_cloud_tab(), "Steam Cloud")
        self.tabs.tabBar().setVisible(False)
        content_layout.addWidget(self.tabs, 1)

        self.nav_buttons: list[QPushButton] = []
        self.nav_labels: tuple[str, ...] = (
            "Обзор",
            "Инвентарь",
            "Изменения",
            "Резервные копии",
            "Steam Cloud",
        )
        for index, label in enumerate(self.nav_labels):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda _checked=False, i=index: self._select_tab(i))
            sidebar_layout.addWidget(button)
            self.nav_buttons.append(button)
        sidebar_layout.addStretch(1)
        self.decoder_status = QLabel("CORE: READY\nCRC / SHA / BACKUP включены")
        self.decoder_status.setObjectName("sidebarStatus")
        self.decoder_status.setWordWrap(True)
        sidebar_layout.addWidget(self.decoder_status)

        body.addWidget(self.sidebar)
        body.addWidget(content_panel, 1)
        layout.addLayout(body, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(18, 0, 18, 14)
        actions.addStretch(1)
        self.preview_button = QPushButton("Предпросмотр")
        self.preview_button.setEnabled(False)
        self.preview_button.setToolTip("Подготовить immutable preview из staged edits")
        self.preview_button.clicked.connect(self._start_preview)
        actions.addWidget(self.preview_button)
        self.save_copy_button = QPushButton("Сохранить копию")
        self.save_copy_button.setEnabled(False)
        self.save_copy_button.setToolTip("Записать только ранее проверенный preview")
        self.save_copy_button.clicked.connect(self._choose_and_start_apply)
        actions.addWidget(self.save_copy_button)
        layout.addLayout(actions)

        self.tabs.currentChanged.connect(self._sync_nav_state)
        self._sync_nav_state(0)

        self.setTabOrder(self.open_button, self.nav_buttons[0])
        self.setTabOrder(self.tabs, self.preview_button)
        self.setTabOrder(self.preview_button, self.save_copy_button)

    def _select_tab(self, index: int) -> None:
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def _sync_nav_state(self, index: int) -> None:
        for button_index, button in enumerate(getattr(self, "nav_buttons", [])):
            button.setChecked(button_index == index)

    def _sync_nav_counters(self) -> None:
        """Show inventory and staged-change counts next to the section names.

        The visual reference carries a badge per section.  Only counts the
        parser or the staging state actually knows are shown; a section with
        nothing to count keeps its bare name.
        """

        buttons = getattr(self, "nav_buttons", [])
        if not buttons:
            return
        inventory = len(self.snapshot.info.inventory) if self.snapshot is not None else None
        staged = len(self.staged_counts) + (1 if self.staged_money is not None else 0)
        counters: dict[int, int | None] = {1: inventory, 2: staged or None}
        for index, button in enumerate(buttons):
            count = counters.get(index)
            label = self.nav_labels[index]
            button.setText(label if count is None else f"{label}  ·  {count}")

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        cards = QFrame()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(8)
        cards_layout.setVerticalSpacing(8)

        def add_card(column: int, caption: str, initial: str) -> QLabel:
            card = QFrame()
            card.setObjectName("metricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 9, 12, 9)
            card_layout.setSpacing(4)
            caption_label = QLabel(caption)
            caption_label.setObjectName("metricCaption")
            card_layout.addWidget(caption_label)
            value_label = QLabel(initial)
            value_label.setObjectName("metricValue")
            card_layout.addWidget(value_label)
            cards_layout.addWidget(card, 0, column)
            return value_label

        self.location_card_value = add_card(0, "Локация", "—")
        self.time_card_value = add_card(1, "Время", "—")
        self.money_card_value = add_card(2, "Деньги", "—")
        self.inventory_card_value = add_card(3, "Предметы", "—")
        layout.addWidget(cards)

        # A word-wrapped QLabel inside a QFormLayout reports a height hint for a
        # single line, so the summary used to render clipped and overlapping.
        # Plain vertical layouts with expanding labels lay wrapped text out
        # correctly.
        details = QFrame()
        details.setObjectName("metricCard")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(12, 10, 12, 10)
        details_layout.setSpacing(6)
        summary_caption = QLabel("Сводка")
        summary_caption.setObjectName("metricCaption")
        details_layout.addWidget(summary_caption)
        self.summary_label = QLabel("Открой локальный .sav для проверки CRC и структуры.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(self.summary_label)
        self.support_label = QLabel("Редактирование отключено до успешного анализа.")
        self.support_label.setWordWrap(True)
        details_layout.addWidget(self.support_label)
        layout.addWidget(details)

        money_box = QGroupBox("Баланс (staged до preview)")
        money_layout = QVBoxLayout(money_box)
        money_layout.setSpacing(6)
        self.money_status_label = QLabel("Баланс не определён")
        self.money_status_label.setWordWrap(True)
        money_layout.addWidget(self.money_status_label)
        money_row = QHBoxLayout()
        money_row.addWidget(QLabel("Новая сумма"))
        self.money_spin = QSpinBox()
        self.money_spin.setRange(0, 2_000_000_000)
        self.money_spin.setEnabled(False)
        self.money_spin.valueChanged.connect(self._on_money_value_changed)
        money_row.addWidget(self.money_spin, 1)
        self.money_stage_button = QPushButton("Застейджить баланс")
        self.money_stage_button.setEnabled(False)
        self.money_stage_button.clicked.connect(self._stage_money)
        money_row.addWidget(self.money_stage_button)
        self.money_clear_button = QPushButton("Очистить")
        self.money_clear_button.setEnabled(False)
        self.money_clear_button.clicked.connect(self._clear_money)
        money_row.addWidget(self.money_clear_button)
        money_layout.addLayout(money_row)
        layout.addWidget(money_box)

        metadata_box = QGroupBox("Технические метаданные контейнера (.sav)")
        metadata_layout = QVBoxLayout(metadata_box)
        metadata_layout.setContentsMargins(10, 10, 10, 10)
        self.metadata_table = QTableWidget(0, 3)
        self.metadata_table.setObjectName("metadataTable")
        self.metadata_table.setHorizontalHeaderLabels(
            ["Параметр", "Значение в сохранении", "Статус"]
        )
        self.metadata_table.verticalHeader().setVisible(False)
        self.metadata_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.metadata_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metadata_table.setAlternatingRowColors(False)
        header = self.metadata_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        metadata_layout.addWidget(self.metadata_table)
        layout.addWidget(metadata_box, 1)
        self._render_metadata_rows(None)
        return tab

    # Rows are parser-backed only.  The visual reference shows GVAS fields this
    # parser cannot prove; inventing them would make an unverified claim look
    # confirmed, so unknown values stay out of the table entirely.
    def _metadata_rows(self, snapshot: LocalSnapshot | None) -> tuple[tuple[str, str, str], ...]:
        if snapshot is None:
            return (
                ("Файл", "—", "не открыт"),
                ("CRC-32", "—", "не проверен"),
                ("SHA-256", "—", "не вычислен"),
            )
        info = snapshot.info
        money = "неизвестно" if info.money is None else str(info.money)
        money_status = (
            "редактируется"
            if info.money is not None and info.money_anchor_count == 1
            else f"read-only (anchor × {info.money_anchor_count})"
        )
        unresolved = len(info.unresolved_handles)
        return (
            ("Файл", snapshot.path.name, _human_size(len(snapshot.data))),
            ("Формат", snapshot.format_id, snapshot.format_title),
            (
                "CRC-32",
                f"{info.stored_crc32:08X}",
                "PASS" if info.crc_ok else f"FAIL (вычислено {info.computed_crc32:08X})",
            ),
            ("SHA-256", info.sha256, "исходный снимок"),
            (
                "Размер контейнера",
                f"{_human_size(info.packed_size)} → {_human_size(info.unpacked_size)}",
                "Kraken распакован",
            ),
            ("Баланс купонов", money, money_status),
            ("Owned handles", str(len(info.owned_handles)), "прочитано"),
            (
                "Grid handles",
                f"{len({item.handle for item in info.inventory})} / {info.grid_handle_count}",
                "разобрано / объявлено",
            ),
            ("Grid cells", str(info.grid_cell_count), "прочитано"),
            ("Объекты инвентаря", str(len(info.inventory)), "в сетке"),
            ("Orphan handles", str(len(info.orphans)), "вне сетки"),
            (
                "Unresolved handles",
                str(unresolved),
                "read-only" if unresolved else "нет",
            ),
            (
                "UE5 GVAS schema",
                "не разобрана",
                "контейнер валиден, схема не подтверждена",
            ),
        )

    def _render_metadata_rows(self, snapshot: LocalSnapshot | None) -> None:
        rows = self._metadata_rows(snapshot)
        self.metadata_table.setRowCount(len(rows))
        for index, (name, value, status) in enumerate(rows):
            for column, text in enumerate((name, value, status)):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.metadata_table.setItem(index, column, item)

    def _build_inventory_tab(self) -> QWidget:
        self.inventory_view = InventoryView(self)
        self.inventory_view.stage_requested.connect(self._stage_stack_change)
        self.inventory_view.clear_selected_requested.connect(self._clear_selected_stack)
        self.inventory_view.clear_all_requested.connect(self._clear_all_stacks)
        # Keep the old attribute available to small integrations while the
        # actual view now uses a stable-handle QAbstractTableModel.
        self.inventory_table = self.inventory_view.table
        self.inventory_model = self.inventory_view.model
        return self.inventory_view

    def _build_changes_tab(self) -> QWidget:
        self.changes_view = ChangesView(self)
        self.changes_view.preview_requested.connect(self._start_preview)
        self.changes_view.apply_requested.connect(self._choose_and_start_apply)
        self.changes_view.choose_output_requested.connect(self._choose_output)
        return self.changes_view

    def _build_backups_tab(self) -> QWidget:
        self.backups_view = BackupView(backup_dirs=backup_dirs(), parent=self)
        self.backups_view.restore_requested.connect(self._start_restore)
        self.backups_view.folder_open_requested.connect(self._open_backup_folder)
        self.backups_view.refresh()
        return self.backups_view

    def _build_cloud_tab(self) -> QWidget:
        self.cloud_view = CloudView(self.service, backup_dir=backup_dirs()[0], parent=self)
        self.cloud_view.snapshot_ready.connect(self._on_cloud_snapshot_ready)
        self.cloud_view.upload_ready.connect(self._on_cloud_upload_ready)
        self.cloud_view.operation_failed.connect(self._on_cloud_operation_failed)
        self.cloud_view.operation_progress.connect(self._on_cloud_progress)
        self.cloud_view.busy_changed.connect(self._on_cloud_busy)
        return self.cloud_view

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
        if self.snapshot is None:
            self.file_source_badge.setText("ЧТЕНИЕ ФАЙЛА")
            self.meta_filename.setText(path.name)
            self.meta_details.setText("Проверка CRC, SHA и структуры…")
            self.integrity_badge.setText("CRC-32: …")
            self.format_badge.setText("UE5 GVAS: анализ…")
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
        display_message = (
            message
            if message.startswith("Error: Формат файла ")
            else f"{filename}: {message}"
        )
        self.error_label.setText(display_message)
        self.error_label.setVisible(True)
        self.analysis_failed.emit(message)

    def _on_inspect_thread_finished(self) -> None:
        self.open_button.setEnabled(True)
        self._inspect_thread = None
        self._inspect_worker = None

    def _render_snapshot(self, snapshot: LocalSnapshot) -> None:
        # Keep the render helper safe for direct synthetic/UI tests as well as
        # the signal path, where _on_analysis_ready already assigned it.
        self.snapshot = snapshot
        info = snapshot.info
        self.staged_counts.clear()
        self.staged_money = None
        self.prepared_edit = None
        self.cloud_view.set_prepared(None)
        crc = "OK" if info.crc_ok else "FAIL"
        money = "unknown" if info.money is None else str(info.money)
        source_label = "Steam Cloud" if snapshot.source_kind == "cloud" else "локальный"
        self.source_label.setText(
            f"Сейв: {snapshot.path.name} • {source_label} • Формат {snapshot.format_id} • "
            f"{_human_size(len(snapshot.data))} • SHA {info.sha256[:12]}…"
        )
        self.file_source_badge.setText(
            "STEAM CLOUD" if snapshot.source_kind == "cloud" else "ЛОКАЛЬНЫЙ ФАЙЛ"
        )
        self.meta_filename.setText(snapshot.path.name)
        self.meta_details.setText(
            f"{_human_size(len(snapshot.data))} • SHA {info.sha256[:12]}…"
        )
        self.integrity_badge.setText(f"CRC-32: {'PASS' if info.crc_ok else 'FAIL'}")
        # The current parser validates the Kraken container and known fields;
        # it does not prove a complete UE5 GVAS schema. Keep that distinction
        # visible instead of copying the reference's demo success badge.
        self.format_badge.setText("UE5 GVAS: НЕ ПОДТВЕРЖДЁН")
        self.location_card_value.setText("—")
        self.time_card_value.setText("—")
        self.money_card_value.setText(money)
        self.inventory_card_value.setText(str(len(info.inventory)))
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
        self._render_metadata_rows(snapshot)
        self._sync_nav_counters()
        self._render_money(info)
        self._render_inventory(info)
        self.changes_view.set_staged(info, self.staged_money, self.staged_counts)
        self.changes_view.invalidate_preview("изменений ещё нет")
        self.status_label.setText("Анализ завершён; snapshot готов")
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.edit_actions_enabled = True
        self._update_action_buttons()

    def _render_inventory(self, info: SaveInfo) -> None:
        self.inventory_view.set_items(info.inventory)
        self.inventory_view.set_staged_counts(self.staged_counts)
        self.inventory_card_value.setText(str(len(info.inventory)))

    def _render_money(self, info: SaveInfo) -> None:
        if info.money is None or info.money_anchor_count != 1:
            self.money_card_value.setText("—")
            self.money_status_label.setText(
                f"Только чтение: wallet anchor найден {info.money_anchor_count} раз(а)"
            )
            self.money_spin.setEnabled(False)
            self.money_stage_button.setEnabled(False)
            self.money_clear_button.setEnabled(False)
            return
        effective = self.staged_money if self.staged_money is not None else info.money
        self.money_card_value.setText(str(effective))
        self.money_status_label.setText(f"{info.money} → {effective}")
        self.money_spin.blockSignals(True)
        self.money_spin.setEnabled(True)
        self.money_spin.setValue(effective)
        self.money_spin.blockSignals(False)
        self.money_stage_button.setEnabled(True)
        self.money_clear_button.setEnabled(self.staged_money is not None)

    def _on_money_value_changed(self, _value: int) -> None:
        if self.snapshot is None or self.snapshot.info.money is None:
            return
        self.money_status_label.setText(
            f"{self.snapshot.info.money} → {self.money_spin.value()}"
        )

    def _stage_money(self) -> None:
        if self.snapshot is None:
            return
        info = self.snapshot.info
        value = self.money_spin.value()
        if info.money is None or info.money_anchor_count != 1:
            self.money_status_label.setText("Только чтение: wallet anchor не подтверждён")
            return
        if not (0 <= value <= 2_000_000_000):
            self.money_status_label.setText("Сумма отклонена: допустим диапазон 0..2000000000")
            return
        self.staged_money = None if value == info.money else value
        self._render_money(info)
        self._render_changes()
        self._invalidate_preview("изменилось staged значение баланса")
        self.status_label.setText(
            f"Staged: money={'нет' if self.staged_money is None else self.staged_money}, "
            f"stacks={len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

    def _clear_money(self) -> None:
        self.staged_money = None
        if self.snapshot is not None:
            self._render_money(self.snapshot.info)
            self._render_changes()
            self._invalidate_preview("staged баланс очищен")
        self.status_label.setText("Staged balance очищен; bytes сейва не изменены")

    def _find_inventory_item(self, handle: int):
        if self.snapshot is None:
            return None
        return next(
            (item for item in self.snapshot.info.inventory if item.handle == int(handle)),
            None,
        )

    def _stage_stack_change(self, handle: int, new_count: int) -> None:
        item = self._find_inventory_item(handle)
        if item is None:
            self.inventory_view.show_editability_message(
                f"Только чтение: handle 0x{int(handle):08X} не найден в текущем snapshot"
            )
            return
        if not (1 <= int(new_count) <= 1_000_000):
            self.inventory_view.show_editability_message(
                "Новое количество отклонено: допустим диапазон 1..1000000"
            )
            return
        if not item.editable_count:
            reason = (
                "count=1"
                if item.count <= 1
                else f"неподтверждённый kind={item.kind_code}"
            )
            self.inventory_view.show_editability_message(f"Только чтение: {reason}")
            return

        value = int(new_count)
        if value == item.count:
            self.staged_counts.pop(item.handle, None)
        else:
            self.staged_counts[item.handle] = value
        self.inventory_view.set_staged_counts(self.staged_counts)
        self._render_changes()
        self._invalidate_preview("изменилось staged значение stack")
        self.status_label.setText(
            f"Staged: {len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

    def _clear_selected_stack(self, handle: int) -> None:
        self.staged_counts.pop(int(handle), None)
        self.inventory_view.set_staged_counts(self.staged_counts)
        self._render_changes()
        self._invalidate_preview("staged stack очищен")
        self.status_label.setText(
            f"Staged: {len(self.staged_counts)}; bytes сейва не изменены — нужен preview"
        )

    def _clear_all_stacks(self) -> None:
        self.staged_counts.clear()
        self.staged_money = None
        if self.snapshot is not None:
            self._render_money(self.snapshot.info)
        self.inventory_view.set_staged_counts(self.staged_counts)
        self._render_changes()
        self._invalidate_preview("все staged-правки очищены")
        self.status_label.setText("Все staged-правки очищены; bytes сейва не изменены")

    def _render_changes(self) -> None:
        self._sync_nav_counters()
        if self.snapshot is None:
            return
        self.changes_view.set_staged(
            self.snapshot.info,
            self.staged_money,
            self.staged_counts,
        )

    def _has_staged_changes(self) -> bool:
        return self.staged_money is not None or bool(self.staged_counts)

    def _update_action_buttons(self) -> None:
        local_busy = self._operation_thread is not None and self._operation_thread.isRunning()
        busy = local_busy or self._cloud_busy
        has_changes = self.edit_actions_enabled and self._has_staged_changes()
        can_preview = has_changes
        can_apply = self.prepared_edit is not None
        self.preview_button.setEnabled(can_preview and not busy)
        self.save_copy_button.setEnabled(can_apply and not busy)
        self.changes_view.set_actions_enabled(
            preview=can_preview,
            apply=can_apply,
            busy=busy,
        )
        self.backups_view.set_busy(busy)
        self.cloud_view.set_external_busy(local_busy if not self._cloud_busy else False)

    def _show_operation_error(self, message: str) -> None:
        self.status_label.setText("Операция не выполнена")
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.changes_view.set_error(message)
        self.backups_view.set_error(message)
        self.cloud_view.set_error(message)
        self.operation_failed.emit(message)

    def _invalidate_preview(self, reason: str) -> None:
        self.prepared_edit = None
        self.changes_view.invalidate_preview(reason)
        self._update_action_buttons()

    def _build_edit_plan(self) -> EditPlan:
        if self.snapshot is None:
            raise SaveError("Сначала проанализируй сейв")
        if not self._has_staged_changes():
            raise SaveError("Нет staged изменений")
        source_kind = self.snapshot.source_kind
        locator = self.snapshot.locator or str(self.snapshot.path)
        if source_kind not in ("local", "cloud"):
            raise SaveError(f"Неизвестный source kind: {source_kind}")
        kind: Literal["local", "cloud"] = "local" if source_kind == "local" else "cloud"
        return EditPlan(
            source=SourceRef(
                kind=kind,
                locator=locator,
                sha256=self.snapshot.info.sha256,
            ),
            money=self.staged_money,
            stacks=tuple(sorted(self.staged_counts.items())),
        )

    def _busy_now(self) -> bool:
        """True while a local operation or a cloud operation is in flight."""

        local = self._operation_thread is not None and self._operation_thread.isRunning()
        return local or self._cloud_busy

    def _start_preview(self) -> None:
        if self._busy_now():
            # Silence here reads as a dead button; the action buttons are also
            # disabled while busy, so this is the keyboard/automation path.
            self.status_label.setText("Дождись завершения текущей операции")
            return
        try:
            plan = self._build_edit_plan()
        except SaveError as exc:
            self._show_operation_error(str(exc))
            return

        self.prepared_edit = None
        self._operation_kind = "preview"
        self.changes_view.clear_error()
        self.changes_view.set_progress("Запуск preview…")
        self.status_label.setText("Preview: подготовка…")
        worker = OperationWorker(
            self.service,
            mode="preview",
            data=self.snapshot.data if self.snapshot is not None else b"",
            plan=plan,
            parent=self,
        )
        worker.preview_ready.connect(self._on_preview_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_thread = worker
        self._update_action_buttons()
        worker.start()

    def _on_preview_ready(self, prepared: PreparedEdit) -> None:
        try:
            current_plan = self._build_edit_plan()
        except SaveError as exc:
            self._on_operation_failed(str(exc))
            return
        if prepared.plan != current_plan:
            self._on_operation_failed("Staged форма изменилась во время preview; повтори preview")
            return
        self.prepared_edit = prepared
        self.changes_view.set_preview(prepared)
        self.cloud_view.set_prepared(prepared)
        self.status_label.setText("Preview готов; можно выбрать путь и сохранить копию")
        self.preview_ready.emit(prepared)

    def _on_operation_progress(self, message: str) -> None:
        self.status_label.setText(message)
        self.changes_view.set_progress(message)
        self.backups_view.set_progress(message)

    def _on_operation_failed(self, message: str) -> None:
        if "SHA256" in message or "Источник изменился" in message:
            self.prepared_edit = None
            self.changes_view.invalidate_preview("source SHA изменился")
        self._show_operation_error(message)

    def _on_operation_finished(self) -> None:
        self._operation_thread = None
        self._operation_kind = None
        self.changes_view.set_busy(False)
        self.backups_view.set_busy(False)
        self._update_action_buttons()

    def _choose_output(self) -> None:
        path = self.changes_view.choose_output()
        if path is not None:
            self.changes_view.set_destination(path)

    def _choose_and_start_apply(self) -> None:
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview; запись без него запрещена")
            return
        if self.snapshot is not None and self.snapshot.source_kind == "cloud":
            self._start_cloud_upload()
            return
        value = self.changes_view.destination_edit.text().strip()
        if not value:
            path = self.changes_view.choose_output()
            if path is None:
                return
        else:
            path = Path(value)
        self._start_apply(path)

    def _start_apply(self, output_path: Path, backup_dir: Path | None = None) -> None:
        if self._busy_now():
            self.status_label.setText("Дождись завершения текущей операции")
            return
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview; запись без него запрещена")
            return
        if self.snapshot is None:
            self._show_operation_error("Нет текущего snapshot для apply")
            return
        if self.snapshot.source_kind == "cloud":
            self._start_cloud_upload()
            return
        try:
            current_plan = self._build_edit_plan()
        except SaveError as exc:
            self._show_operation_error(str(exc))
            return
        if self.prepared_edit.plan != current_plan:
            self._invalidate_preview("staged форма изменилась после preview")
            self._show_operation_error("Preview устарел после изменения формы; создай его заново")
            return

        source_path = Path(self.snapshot.path)
        output_path = Path(output_path).expanduser()
        backup_path = Path(backup_dir).expanduser() if backup_dir is not None else backup_dirs()[0]
        worker = OperationWorker(
            self.service,
            mode="apply",
            data=self.snapshot.data,
            plan=self.prepared_edit.plan,
            source_path=source_path,
            output_path=output_path,
            backup_dir=backup_path,
            parent=self,
        )
        worker.set_prepared(self.prepared_edit)
        worker.preview_ready.connect(self._on_preview_ready)
        worker.apply_ready.connect(self._on_apply_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_kind = "apply"
        self._operation_thread = worker
        self.changes_view.set_destination(output_path)
        self.changes_view.set_progress("Запуск local export…")
        self.status_label.setText("Сохранение копии…")
        self._update_action_buttons()
        worker.start()

    def _on_apply_ready(self, receipt) -> None:
        self.prepared_edit = None
        self.changes_view.mark_applied(receipt)
        self.status_label.setText(f"Копия сохранена: {receipt.output_path}")
        self.apply_ready.emit(receipt)

    def _start_restore(self, record, output_path: Path) -> None:
        if self._operation_thread is not None and self._operation_thread.isRunning():
            return
        if getattr(record, "status", None) != "verified":
            self._show_operation_error("Выбранный backup не прошёл проверку SHA256")
            return
        worker = RestoreWorker(self.service, record, Path(output_path), parent=self)
        worker.completed.connect(self._on_restore_ready)
        worker.failed.connect(self._on_operation_failed)
        worker.progress.connect(self._on_operation_progress)
        worker.finished.connect(self._on_operation_finished)
        worker.finished.connect(worker.deleteLater)
        self._operation_kind = "restore"
        self._operation_thread = worker
        self.backups_view.set_progress("Запуск restore…")
        self.status_label.setText("Восстановление копии…")
        self._update_action_buttons()
        worker.start()

    def _on_restore_ready(self, receipt) -> None:
        self.backups_view.mark_restored(receipt)
        self.status_label.setText(f"Копия восстановлена: {receipt.output_path}")
        self.restore_ready.emit(receipt)

    def _on_cloud_snapshot_ready(self, snapshot: CloudSnapshot) -> None:
        local_snapshot = LocalSnapshot(
            path=Path(snapshot.name),
            data=snapshot.data,
            info=snapshot.info,
            source_kind="cloud",
            locator=snapshot.name,
            format_id=snapshot.format_id,
            format_title=snapshot.format_title,
        )
        self._render_snapshot(local_snapshot)
        self.analysis_ready.emit(local_snapshot)
        self.status_label.setText(
            f"Cloud snapshot готов: {snapshot.name}; выбери изменения и создай preview"
        )

    def _start_cloud_upload(self) -> None:
        if self.prepared_edit is None:
            self._show_operation_error("Сначала создай preview cloud-сейва")
            return
        self.status_label.setText("Cloud upload: подготовка…")
        self.cloud_view.start_upload()

    def _on_cloud_upload_ready(self, receipt) -> None:
        self.prepared_edit = None
        self.status_label.setText(
            "Cloud: verified" if receipt.status == "verified" else "Cloud: uncertain — требуется reconciliation"
        )
        self._update_action_buttons()
        self.apply_ready.emit(receipt)

    def _on_cloud_operation_failed(self, message: str) -> None:
        self._show_operation_error(message)

    def _on_cloud_progress(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_cloud_busy(self, busy: bool) -> None:
        self._cloud_busy = busy
        self._update_action_buttons()

    def _open_backup_folder(self, path: Path) -> None:
        folder = Path(path).expanduser()
        if not folder.is_dir():
            self._show_operation_error(f"Папка backup не существует: {folder}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self._show_operation_error(f"Не удалось открыть папку backup: {folder}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._operation_thread is not None and self._operation_thread.isRunning():
            self.status_label.setText(
                "Операция ещё выполняется; закрой окно после завершения, чтобы не оборвать запись"
            )
            event.ignore()
            return
        if self.cloud_view.is_busy:
            self.status_label.setText(
                "Cloud operation ещё выполняется; закрой окно после завершения"
            )
            event.ignore()
            return
        if self._inspect_thread is not None and self._inspect_thread.isRunning():
            self._inspect_thread.quit()
            self._inspect_thread.wait(10_000)
        # A QThread destroyed while running aborts the process, so the window
        # never closes over one that is still alive.
        if self._operation_thread is not None and self._operation_thread.isRunning():
            self._operation_thread.quit()
            self._operation_thread.wait(10_000)
        self.cloud_view.close()
        event.accept()


__all__ = ["InspectWorker", "LocalSnapshot", "MainWindow"]
