"""Compact goodwill controls for the original X-Ray relation registry."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
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

from editor.catalog import FactionCatalog, FactionDefinition
from save_format import SaveInfo


class FactionView(QGroupBox):
    """Show and stage actor community/goodwill values from one catalog."""

    relation_stage_requested = Signal(str, int)
    player_faction_stage_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Отношения с группировками", parent)
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

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        player_row = QHBoxLayout()
        player_row.setSpacing(6)
        player_row.addWidget(QLabel("Группировка игрока"))
        self.player_faction_current = QLabel("неизвестно")
        self.player_faction_current.setObjectName("playerFactionCurrent")
        self.player_faction_current.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        player_row.addWidget(self.player_faction_current, 1)
        self.player_faction_combo = QComboBox()
        self.player_faction_combo.setObjectName("playerFactionCombo")
        player_row.addWidget(self.player_faction_combo)
        self.player_faction_stage_button = QPushButton("Застейджить")
        self.player_faction_stage_button.setObjectName("playerFactionStageButton")
        self.player_faction_stage_button.clicked.connect(self._stage_player_faction)
        player_row.addWidget(self.player_faction_stage_button)
        layout.addLayout(player_row)

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
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.relations_table)

    def set_catalog(
        self,
        catalog: FactionCatalog | None,
        *,
        relation_enabled: bool,
        player_enabled: bool = False,
        reason: str | None = None,
    ) -> None:
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

    def _set_empty_table(self, message: str) -> None:
        self.relations_table.clearSpans()
        self.relations_table.setRowCount(1)
        self.relations_table.setSpan(0, 0, 1, 4)
        item = QTableWidgetItem(message)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.relations_table.setItem(0, 0, item)
        for column in range(1, 4):
            self.relations_table.setItem(0, column, QTableWidgetItem(""))

    def _render(self) -> None:
        info = self._info
        catalog = self._catalog
        if info is None:
            self.player_faction_current.setText("неизвестно")
            self.player_faction_combo.clear()
            self.player_faction_combo.setEnabled(False)
            self.player_faction_stage_button.setEnabled(False)
            self.status_label.setText(self._reason or "Сейв ещё не проанализирован.")
            self.warning_label.clear()
            self.warning_label.setVisible(False)
            self._set_empty_table("Значения появятся после анализа X-Ray сейва.")
            return
        if catalog is None or not catalog.factions:
            self.player_faction_current.setText("неизвестно")
            self.player_faction_combo.clear()
            self.player_faction_combo.setEnabled(False)
            self.player_faction_stage_button.setEnabled(False)
            self.status_label.setText(
                self._reason or "Официальный faction catalog для этого релиза недоступен."
            )
            self._set_empty_table("Relation registry или официальный каталог недоступен.")
            return

        limits = (
            f"goodwill {catalog.goodwill_min}…{catalog.goodwill_max}"
            if catalog.goodwill_min is not None and catalog.goodwill_max is not None
            else "диапазон goodwill не задан"
        )
        self.status_label.setText(
            f"{self._reason + '; ' if self._reason else ''}"
            f"Загружено группировок: {len(catalog.factions)}; {limits}. "
            "Изменения staged, исходный сейв не изменён."
        )
        self.warning_label.setText(
            self._warning_text(catalog)
        )
        self.warning_label.setVisible(True)

        rows = [faction for faction in catalog.factions if faction.numeric_id is not None]
        self._render_player_faction(info, rows)

        current = dict(info.faction_relations)
        self.relations_table.clearSpans()
        self.relations_table.setRowCount(len(rows) or 1)
        if not rows:
            self._set_empty_table("В каталоге нет подтверждённых numeric community id.")
            return
        min_value = catalog.goodwill_min if catalog.goodwill_min is not None else -2_147_483_648
        max_value = catalog.goodwill_max if catalog.goodwill_max is not None else 2_147_483_647
        for row_index, faction in enumerate(rows):
            assert faction.numeric_id is not None
            key = faction.key
            name = QTableWidgetItem(self._display_faction(key))
            name.setToolTip(f"community id: {faction.numeric_id}")
            stored = faction.numeric_id in current
            current_item = QTableWidgetItem(
                str(current.get(faction.numeric_id, 0)) if stored else "0 (default)"
            )
            spin = QSpinBox()
            spin.setRange(min_value, max_value)
            spin.setValue(self._staged_relations.get(key, current.get(faction.numeric_id, 0)))
            spin.setEnabled(self._relation_enabled)
            button = QPushButton(
                "Отношение*" if key in self._staged_relations else "Застейджить"
            )
            button.setEnabled(self._relation_enabled)
            button.clicked.connect(partial(self._stage_relation, key, spin))
            self.relations_table.setItem(row_index, 0, name)
            self.relations_table.setItem(row_index, 1, current_item)
            self.relations_table.setCellWidget(row_index, 2, spin)
            self.relations_table.setCellWidget(row_index, 3, button)

    def _stage_relation(self, key: str, spin: QSpinBox) -> None:
        self.relation_stage_requested.emit(key, spin.value())

    def _warning_text(self, catalog: FactionCatalog) -> str:
        game = catalog.release_id
        if game == "stalker-cs":
            player_warning = (
                "ЧН: сюжетные скрипты могут перезаписать community игрока до "
                "нужной миссии."
            )
        elif game == "stalker-soc":
            player_warning = (
                "ТЧ: сюжетные скрипты могут пересчитать community игрока после "
                "загрузки сейва."
            )
        else:
            player_warning = (
                "ЗП: сюжетные скрипты могут пересчитать community игрока после "
                "загрузки сейва."
            )
        return (
            "Сюжет и AI могут пересчитать goodwill после загрузки. "
            f"{player_warning} Перед записью сделай backup исходного сейва."
        )

    def _render_player_faction(
        self, info: SaveInfo, rows: list[FactionDefinition]
    ) -> None:
        # FactionDefinition is intentionally accessed through its public
        # attributes; the catalog remains the single source of display names.
        catalog = self._catalog
        if catalog is None:
            return
        self.player_faction_combo.blockSignals(True)
        self.player_faction_combo.clear()
        for faction in rows:
            key = str(faction.key)
            self.player_faction_combo.addItem(self._display_faction(key), key)
        self.player_faction_combo.blockSignals(False)

        current = catalog.resolve_numeric(info.player_faction_index) if info.player_faction_index is not None else None
        self.player_faction_current.setText(
            self._display_faction(current.key)
            if current is not None
            else (
                "неизвестно"
                if info.player_faction_index is None
                else f"community id {info.player_faction_index} (нет в каталоге)"
            )
        )
        staged = self._staged_player_faction
        selected_key = staged or (current.key if current is not None else None)
        selected_index = self.player_faction_combo.findData(selected_key)
        if selected_index < 0 and rows:
            selected_index = 0
        self.player_faction_combo.setCurrentIndex(selected_index)
        enabled = bool(
            self._player_enabled
            and info.player_faction_editable
            and rows
        )
        self.player_faction_combo.setEnabled(enabled)
        self.player_faction_stage_button.setEnabled(enabled)
        self.player_faction_stage_button.setText(
            "Группировка*" if staged is not None else "Застейджить"
        )

    def _stage_player_faction(self) -> None:
        index = self.player_faction_combo.currentIndex()
        if index < 0:
            return
        key = self.player_faction_combo.itemData(index)
        if isinstance(key, str) and key:
            self.player_faction_stage_requested.emit(key)


__all__ = ["FactionView"]
