"""Compact goodwill controls for the original X-Ray relation registry."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
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
    """Show and stage actor goodwill values from one release-scoped catalog."""

    relation_stage_requested = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Отношения с группировками", parent)
        self._catalog: FactionCatalog | None = None
        self._info: SaveInfo | None = None
        self._relation_enabled = False
        self._reason: str | None = None
        self._staged_relations: dict[str, int] = {}
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
        reason: str | None = None,
    ) -> None:
        self._catalog = catalog
        self._relation_enabled = bool(relation_enabled and catalog is not None)
        self._reason = reason
        self._render()

    def set_state(
        self,
        info: SaveInfo | None,
        staged_relations: Mapping[str, int] | None = None,
    ) -> None:
        self._info = info
        self._staged_relations = {
            str(key): int(value) for key, value in (staged_relations or {}).items()
        }
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
            self.status_label.setText(self._reason or "Сейв ещё не проанализирован.")
            self.warning_label.clear()
            self.warning_label.setVisible(False)
            self._set_empty_table("Значения появятся после анализа X-Ray сейва.")
            return
        if catalog is None or not catalog.factions:
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
            "Сюжет и AI могут пересчитать goodwill после загрузки. Перед записью "
            "сделай backup исходного сейва."
        )
        self.warning_label.setVisible(True)

        current = dict(info.faction_relations)
        rows = [faction for faction in catalog.factions if faction.numeric_id is not None]
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


__all__ = ["FactionView"]
