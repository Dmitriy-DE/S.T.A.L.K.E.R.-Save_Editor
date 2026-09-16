"""Compact X-Ray community controls for the Qt shell.

The view is deliberately a presentation boundary.  It only offers a catalog
entry when the parser supplied the matching numeric community id; mutation
permission remains a capability decision owned by :class:`MainWindow`.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.catalog import FactionCatalog
from save_format import SaveInfo


class FactionView(QGroupBox):
    """Show player community and actor goodwill rows from one X-Ray save."""

    relation_stage_requested = Signal(str, int)
    player_faction_stage_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Группировка и отношения", parent)
        self._catalog: FactionCatalog | None = None
        self._info: SaveInfo | None = None
        self._relation_enabled = False
        self._player_enabled = False
        self._reason: str | None = None
        self._staged_relations: dict[str, int] = {}
        self._staged_player_faction: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)

        self.status_label = QLabel("Открой X-Ray сейв с официальным каталогом.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        player_form = QFormLayout()
        self.player_faction_current = QLabel("неизвестно")
        self.player_faction_current.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        player_form.addRow("Текущая группировка", self.player_faction_current)

        player_row = QHBoxLayout()
        self.player_faction_combo = QComboBox()
        self.player_faction_combo.setMinimumContentsLength(24)
        player_row.addWidget(self.player_faction_combo, 1)
        self.player_faction_stage_button = QPushButton("Застейджить")
        self.player_faction_stage_button.setEnabled(False)
        self.player_faction_stage_button.clicked.connect(self._stage_player_faction)
        player_row.addWidget(self.player_faction_stage_button)
        player_form.addRow("Новая группировка", player_row)
        layout.addLayout(player_form)

        self.warning_label = QLabel("")
        self.warning_label.setObjectName("factionWarning")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        self.relations_table = QTableWidget(0, 4)
        self.relations_table.setObjectName("factionRelationsTable")
        self.relations_table.setHorizontalHeaderLabels(
            ["Группировка", "Текущее goodwill", "Новое", "Действие"]
        )
        self.relations_table.verticalHeader().setVisible(False)
        self.relations_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.relations_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.relations_table.setAlternatingRowColors(True)
        self.relations_table.setMaximumHeight(210)
        header = self.relations_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.relations_table)

    def set_catalog(
        self,
        catalog: FactionCatalog | None,
        *,
        relation_enabled: bool,
        player_enabled: bool,
        reason: str | None = None,
    ) -> None:
        """Set the release catalog and the independent mutation gates."""

        self._catalog = catalog
        self._relation_enabled = bool(relation_enabled and catalog is not None)
        self._player_enabled = bool(player_enabled and catalog is not None)
        self._reason = reason
        self._render()

    def set_state(
        self,
        info: SaveInfo | None,
        staged_relations: Mapping[str, int] | None = None,
        staged_player_faction: str | None = None,
    ) -> None:
        """Render one immutable save snapshot plus unapplied UI changes."""

        self._info = info
        self._staged_relations = {
            str(key): int(value) for key, value in (staged_relations or {}).items()
        }
        self._staged_player_faction = staged_player_faction
        self._render()

    def _display_faction(self, key: str) -> str:
        if self._catalog is None:
            return key
        faction = self._catalog.resolve(key)
        label = faction.display_name or faction.key
        return label if label == faction.key else f"{label} · {faction.key}"

    def _display_numeric(self, numeric_id: int | None) -> str:
        if numeric_id is None:
            return "неизвестно"
        if self._catalog is None:
            return f"неизвестно · #{numeric_id}"
        faction = self._catalog.resolve_numeric(numeric_id)
        if faction is None:
            return f"неизвестно · #{numeric_id}"
        return f"{self._display_faction(faction.key)} · #{numeric_id}"

    def _render(self) -> None:
        info = self._info
        catalog = self._catalog
        if info is None:
            self.status_label.setText(self._reason or "Сейв ещё не проанализирован.")
            self.player_faction_current.setText("неизвестно")
            self.player_faction_combo.clear()
            self.player_faction_combo.setEnabled(False)
            self.player_faction_stage_button.setEnabled(False)
            self._set_empty_table("Значения появятся после анализа X-Ray сейва.")
            self.warning_label.clear()
            self.warning_label.setVisible(False)
            return

        self.player_faction_current.setText(self._display_numeric(info.player_faction_index))
        self.player_faction_combo.blockSignals(True)
        self.player_faction_combo.clear()
        for faction in catalog.factions if catalog is not None else ():
            if faction.numeric_id is None:
                continue
            self.player_faction_combo.addItem(
                self._display_faction(faction.key), faction.key
            )
        if self._staged_player_faction is not None:
            index = self.player_faction_combo.findData(self._staged_player_faction)
            if index >= 0:
                self.player_faction_combo.setCurrentIndex(index)
        elif catalog is not None and info.player_faction_index is not None:
            current = catalog.resolve_numeric(info.player_faction_index)
            if current is not None:
                index = self.player_faction_combo.findData(current.key)
                if index >= 0:
                    self.player_faction_combo.setCurrentIndex(index)
        self.player_faction_combo.blockSignals(False)
        player_allowed = bool(
            self._player_enabled and self.player_faction_combo.count() > 0
        )
        self.player_faction_combo.setEnabled(player_allowed)
        self.player_faction_stage_button.setEnabled(player_allowed)
        self.player_faction_stage_button.setText(
            "Группировка*" if self._staged_player_faction is not None else "Застейджить"
        )

        if catalog is None or not catalog.factions:
            self.status_label.setText(
                self._reason or "Официальный faction catalog для этого релиза недоступен."
            )
        elif self._relation_enabled:
            limits = (
                f"goodwill {catalog.goodwill_min}…{catalog.goodwill_max}"
                if catalog.goodwill_min is not None and catalog.goodwill_max is not None
                else "диапазон goodwill не задан"
            )
            self.status_label.setText(
                f"{self._reason + '; ' if self._reason else ''}"
                f"Загружено группировок: {len(catalog.factions)}; {limits}. "
                "Правки пока staged, исходный сейв не изменён."
            )
        else:
            self.status_label.setText(
                self._reason
                or "Группировки прочитаны; запись остаётся read-only до игрового evidence."
            )

        release_id = catalog.release_id if catalog is not None else ""
        if release_id == "stalker-cs":
            self.warning_label.setText(
                "ЧН: принадлежность Шрама может быть перезаписана сюжетным скриптом "
                "до нужной миссии; редактор квесты не моделирует."
            )
            self.warning_label.setVisible(True)
        elif release_id in {"stalker-soc", "stalker-cop"}:
            self.warning_label.setText(
                "Поле community участвует в расчёте отношений; сюжетный скрипт может "
                "перезаписать его после загрузки. Условия этого сейва не подтверждены."
            )
            self.warning_label.setVisible(True)
        else:
            self.warning_label.clear()
            self.warning_label.setVisible(False)

        self._render_relations(info, catalog)

    def _set_empty_table(self, message: str) -> None:
        self.relations_table.clearSpans()
        self.relations_table.setRowCount(1)
        self.relations_table.setSpan(0, 0, 1, 4)
        item = QTableWidgetItem(message)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.relations_table.setItem(0, 0, item)
        for column in range(1, 4):
            self.relations_table.setItem(0, column, QTableWidgetItem(""))

    def _render_relations(
        self,
        info: SaveInfo,
        catalog: FactionCatalog | None,
    ) -> None:
        if catalog is None or not catalog.factions:
            self._set_empty_table("Relation registry или официальный каталог недоступен.")
            return

        current = dict(info.faction_relations)
        rows = [faction for faction in catalog.factions if faction.numeric_id is not None]
        if not rows:
            self._set_empty_table("В каталоге нет числовых community id.")
            return
        self.relations_table.clearSpans()
        self.relations_table.setRowCount(len(rows))
        min_value = catalog.goodwill_min if catalog.goodwill_min is not None else -2_147_483_648
        max_value = catalog.goodwill_max if catalog.goodwill_max is not None else 2_147_483_647
        for row_index, faction in enumerate(rows):
            numeric_id = faction.numeric_id
            if numeric_id is None:
                continue
            name = QTableWidgetItem(self._display_faction(faction.key))
            name.setToolTip(f"community id: {numeric_id}")
            stored = numeric_id in current
            current_item = QTableWidgetItem(
                str(current.get(numeric_id, 0)) if stored else "0 (default)"
            )
            spin = QSpinBox()
            spin.setRange(min_value, max_value)
            spin.setValue(self._staged_relations.get(faction.key, current.get(numeric_id, 0)))
            spin.setEnabled(self._relation_enabled)
            self.relations_table.setItem(row_index, 0, name)
            self.relations_table.setItem(row_index, 1, current_item)
            self.relations_table.setCellWidget(row_index, 2, spin)
            button = QPushButton(
                "Отношение*" if faction.key in self._staged_relations else "Застейджить"
            )
            button.setEnabled(self._relation_enabled)
            button.clicked.connect(partial(self._stage_relation, faction.key, spin))
            self.relations_table.setCellWidget(row_index, 3, button)

    def _stage_relation(self, key: str, spin: QSpinBox) -> None:
        self.relation_stage_requested.emit(key, spin.value())

    def _stage_player_faction(self) -> None:
        key = self.player_faction_combo.currentData()
        if key:
            self.player_faction_stage_requested.emit(str(key))


__all__ = ["FactionView"]
