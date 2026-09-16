"""Preview and local-apply controls for the optional Qt shell."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.catalog import FactionCatalog, UpgradeCatalog
from editor.models import PreparedEdit
from save_format import SaveInfo


class ChangesView(QWidget):
    """Read-only staged-change list and preview/apply actions."""

    preview_requested = Signal()
    apply_requested = Signal()
    replace_requested = Signal()
    choose_output_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.staged_label = QLabel("Нет staged changes")
        self.staged_label.setWordWrap(True)
        layout.addWidget(self.staged_label)

        self.changes_table = QTableWidget(0, 5)
        self.changes_table.setHorizontalHeaderLabels(
            ["Операция", "Handle/поле", "До", "После", "Поддержка"]
        )
        self.changes_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.changes_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.changes_table.setAlternatingRowColors(True)
        self.changes_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.changes_table, 1)

        destination = QFormLayout()
        destination_row = QHBoxLayout()
        self.destination_edit = QLineEdit()
        self.destination_edit.setPlaceholderText("Путь новой копии сохранения")
        destination_row.addWidget(self.destination_edit, 1)
        self.choose_output_button = QPushButton("Выбрать…")
        self.choose_output_button.clicked.connect(self.choose_output_requested.emit)
        destination_row.addWidget(self.choose_output_button)
        destination.addRow("Копия", destination_row)
        layout.addLayout(destination)

        actions = QHBoxLayout()
        self.preview_button = QPushButton("Проверить preview")
        self.preview_button.setEnabled(False)
        self.preview_button.clicked.connect(self.preview_requested.emit)
        actions.addWidget(self.preview_button)
        self.apply_button = QPushButton("Сохранить копию")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_requested.emit)
        actions.addWidget(self.apply_button)
        self.replace_button = QPushButton("Заменить исходный слот…")
        self.replace_button.setEnabled(False)
        self.replace_button.setToolTip(
            "Явно заменить выбранный слот после backup и preview"
        )
        self.replace_button.clicked.connect(self.replace_requested.emit)
        actions.addWidget(self.replace_button)
        self.cloud_button = QPushButton("Загрузить в Steam")
        self.cloud_button.setEnabled(False)
        self.cloud_button.setToolTip("Cloud UI подключается в U06")
        actions.addWidget(self.cloud_button)
        layout.addLayout(actions)

        self.preview_status_label = QLabel("Preview ещё не создан")
        self.preview_status_label.setWordWrap(True)
        self.preview_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.preview_status_label)
        self.progress_label = QLabel("")
        self.progress_label.setWordWrap(True)
        layout.addWidget(self.progress_label)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #a11;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

    def set_staged(
        self,
        info: SaveInfo,
        staged_money: int | None,
        staged_counts: Mapping[int, int],
        staged_adds: Mapping[str, int] | None = None,
        staged_detach: Mapping[int, bool] | None = None,
        staged_durability: Mapping[int, float] | None = None,
        staged_faction_relations: Mapping[str, int] | None = None,
        faction_catalog: FactionCatalog | None = None,
        staged_player_faction: str | None = None,
        staged_upgrades: Mapping[int, tuple[str, ...]] | None = None,
        upgrade_catalog: UpgradeCatalog | None = None,
    ) -> None:
        staged_adds = staged_adds or {}
        staged_detach = staged_detach or {}
        staged_durability = staged_durability or {}
        staged_faction_relations = staged_faction_relations or {}
        staged_upgrades = staged_upgrades or {}

        def item_risk(text: str) -> str:
            return f"ОПАСНО: {text}; backup обязателен"

        items = {item.handle: item for item in info.inventory}
        rows: list[tuple[str, str, str, str, str]] = []
        if staged_money is not None:
            before = "unknown" if info.money is None else str(info.money)
            rows.append(("Баланс", "money", before, str(staged_money), "Подтверждено"))
        for handle, new_count in sorted(staged_counts.items()):
            item = items.get(int(handle))
            if item is None:
                rows.append(
                    (
                        "Стак",
                        f"0x{int(handle):08X}",
                        "unknown",
                        str(new_count),
                        "Только чтение: handle не найден",
                    )
                )
                continue
            rows.append(
                (
                    "Стак",
                    item.handle_hex,
                    str(item.count),
                    str(new_count),
                    "Количество можно изменить" if item.editable_count else "Только чтение",
                )
            )
        for item_key, quantity in sorted(staged_adds.items()):
            rows.append(
                (
                    "Добавление",
                    item_key,
                    "—",
                    f"× {quantity}",
                    item_risk("Официальный serializer family"),
                )
            )
        for handle, deep in sorted(staged_detach.items()):
            item = items.get(int(handle))
            rows.append(
                (
                    "Удаление",
                    item.handle_hex if item is not None else f"0x{int(handle):08X}",
                    item.type_key if item is not None else "unknown",
                    "удалить",
                    item_risk("registry deep detach") if deep else "только чтение",
                )
            )
        for handle, condition in sorted(staged_durability.items()):
            item = items.get(int(handle))
            before = (
                f"{item.condition * 100.0:.1f}%"
                if item is not None and item.condition is not None
                else "unknown"
            )
            rows.append(
                (
                    "Прочность",
                    item.handle_hex if item is not None else f"0x{int(handle):08X}",
                    before,
                    f"{float(condition) * 100.0:.1f}%",
                    "STATE f32 + UPDATE q8 + client-data mirror"
                    if item is not None and item.condition_editable
                    else "Только чтение",
                )
            )
        current_relations = dict(info.faction_relations)
        for key, goodwill in sorted(staged_faction_relations.items()):
            faction = faction_catalog.resolve(key) if faction_catalog is not None else None
            numeric_id = faction.numeric_id if faction is not None else None
            before = (
                str(current_relations[numeric_id])
                if numeric_id is not None and numeric_id in current_relations
                else "0 (default)"
            )
            label = (
                f"{faction.display_name or faction.key} · {faction.key}"
                if faction is not None and faction.display_name not in (None, faction.key)
                else faction.key if faction is not None else key
            )
            rows.append(
                (
                    "Отношение",
                    label,
                    before,
                    str(goodwill),
                    "С риском: Relation registry; round-trip проверка; backup обязателен",
                )
            )
        if staged_player_faction is not None:
            selected = (
                faction_catalog.resolve(staged_player_faction)
                if faction_catalog is not None
                else None
            )
            current = (
                faction_catalog.resolve_numeric(info.player_faction_index)
                if faction_catalog is not None and info.player_faction_index is not None
                else None
            )

            def faction_label(faction: object | None, fallback: str) -> str:
                if faction is None:
                    return fallback
                key = str(getattr(faction, "key", fallback))
                name = getattr(faction, "display_name", None) or key
                return key if name == key else f"{name} · {key}"

            rows.append(
                (
                    "Группировка игрока",
                    "actor community",
                    faction_label(
                        current,
                        (
                            "неизвестно"
                            if info.player_faction_index is None
                            else f"community id {info.player_faction_index}"
                        ),
                    ),
                    faction_label(selected, staged_player_faction),
                    "ОПАСНО: actor STATE community; сюжет может перезаписать; backup обязателен",
                )
            )
        for handle, values in sorted(staged_upgrades.items()):
            item = items.get(int(handle))
            before_values = item.upgrades if item is not None else None
            display_values = tuple(str(value) for value in values)
            rows.append(
                (
                    "Улучшения",
                    item.handle_hex if item is not None else f"0x{int(handle):08X}",
                    "unknown"
                    if before_values is None
                    else ", ".join(before_values) or "нет",
                    ", ".join(display_values) or "нет",
                    item_risk(
                        "STATE m_upgrades vector; официальный catalog"
                        if upgrade_catalog is not None
                        else "STATE m_upgrades vector"
                    ),
                )
            )

        self.changes_table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.changes_table.setItem(row, column, QTableWidgetItem(value))
        self.staged_label.setText(
            f"Staged changes: {len(rows)}; bytes исходного сейва не изменены"
            if rows
            else "Нет staged changes"
        )
        self.preview_button.setEnabled(bool(rows))
        self.error_label.clear()
        self.error_label.setVisible(False)

    def set_preview(self, prepared: PreparedEdit) -> None:
        self.preview_status_label.setText(
            f"Preview готов: input SHA {prepared.plan.source.sha256[:12]}… → "
            f"output {len(prepared.data)} B, SHA {prepared.output_sha256[:12]}…"
        )
        self.progress_label.setText("Preview проверен: CRC/round-trip прошли")
        self.apply_button.setEnabled(True)
        # MainWindow enables in-place replacement only after the worker has
        # finished and has confirmed that the snapshot is a local save.
        self.replace_button.setEnabled(False)
        self.error_label.clear()
        self.error_label.setVisible(False)

    def invalidate_preview(self, reason: str) -> None:
        self.preview_status_label.setText(f"Preview недействителен: {reason}")
        self.apply_button.setEnabled(False)
        self.replace_button.setEnabled(False)

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.preview_button.setEnabled(False)
            self.apply_button.setEnabled(False)
            self.replace_button.setEnabled(False)
        self.choose_output_button.setEnabled(not busy)
        self.destination_edit.setEnabled(not busy)
        self.cloud_button.setEnabled(False)

    def set_actions_enabled(
        self, *, preview: bool, apply: bool, replace: bool = False, busy: bool
    ) -> None:
        """Set action state from MainWindow's single operation gate."""

        self.preview_button.setEnabled(bool(preview) and not busy)
        self.apply_button.setEnabled(bool(apply) and not busy)
        self.replace_button.setEnabled(bool(replace) and not busy)
        self.choose_output_button.setEnabled(not busy)
        self.destination_edit.setEnabled(not busy)
        self.cloud_button.setEnabled(False)

    def set_progress(self, message: str) -> None:
        self.progress_label.setText(message)

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.progress_label.setText("Операция остановлена")

    def clear_error(self) -> None:
        self.error_label.clear()
        self.error_label.setVisible(False)

    def mark_applied(self, receipt) -> None:
        output = Path(receipt.output_path)
        backup = Path(receipt.backup_path)
        self.preview_status_label.setText(
            f"Сохранено: {output} • backup: {backup} • SHA {receipt.output_sha256[:12]}…"
        )
        self.progress_label.setText("Local export подтверждён read-back SHA")
        self.apply_button.setEnabled(False)
        self.replace_button.setEnabled(False)

    def mark_replaced(self, receipt) -> None:
        output = Path(receipt.output_path)
        backup = Path(receipt.backup_path)
        self.preview_status_label.setText(
            f"Исходный слот заменён: {output} • backup: {backup} • "
            f"SHA {receipt.output_sha256[:12]}…"
        )
        self.progress_label.setText("Local replace подтверждён read-back SHA")
        self.apply_button.setEnabled(False)
        self.replace_button.setEnabled(False)

    def choose_output(self) -> Path | None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить копию S.T.A.L.K.E.R.",
            self.destination_edit.text(),
            "S.T.A.L.K.E.R. saves (*.sav *.scop *.scs);;Все файлы (*)",
        )
        return Path(filename) if filename else None

    def set_destination(self, path: Path) -> None:
        self.destination_edit.setText(str(path))


__all__ = ["ChangesView"]
