"""X-Ray character and faction state, shown only for supported releases."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.releases import is_xray_original_release

from .style_components import action_button, panel, reference_game_rail, section_header, status_chip


class CharacterView(QWidget):
    """Render parser-backed X-Ray actor data without inventing S2 controls."""

    back_requested = Signal()
    relation_stage_requested = Signal(str, int)
    player_faction_stage_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("characterView")
        self.snapshot: Any | None = None
        self.editable = False
        self._staged: Mapping[str, int] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 20, 0, 0)
        root.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("ПЕРСОНАЖ И ГРУППИРОВКИ (X-RAY)", self))
        self.status_chip = status_chip("ТОЛЬКО X-RAY", self, tone="neutral")
        heading.addStretch(1)
        heading.addWidget(self.status_chip)
        root.addLayout(heading)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(
            reference_game_rail(
                self,
                object_name="characterGameRail",
                active_family="cop",
            ),
            0,
        )
        workspace = QHBoxLayout()
        workspace.setSpacing(10)
        profile = panel(self, object_name="characterProfilePanel")
        profile_layout = QVBoxLayout(profile)
        profile_layout.setContentsMargins(12, 12, 12, 12)
        profile_layout.addWidget(section_header("ПЕРСОНАЖ", "АКТЁР SAVE", profile))
        self.profile_label = QLabel("Сейв не проанализирован", profile)
        self.profile_label.setObjectName("characterProfileLabel")
        self.profile_label.setWordWrap(True)
        profile_layout.addWidget(self.profile_label)
        self.player_faction_label = QLabel("Группировка: неизвестно", profile)
        profile_layout.addWidget(self.player_faction_label)
        self.player_faction_combo = QComboBox(profile)
        self.player_faction_combo.setEnabled(False)
        profile_layout.addWidget(self.player_faction_combo)
        self.player_faction_button = action_button("ИЗМЕНИТЬ", profile)
        self.player_faction_button.setEnabled(False)
        self.player_faction_button.clicked.connect(self._stage_player_faction)
        profile_layout.addWidget(self.player_faction_button)
        facts_panel = panel(profile, object_name="characterFactsPanel")
        facts_layout = QGridLayout(facts_panel)
        facts_layout.setContentsMargins(8, 8, 8, 8)
        facts_layout.setHorizontalSpacing(18)
        facts_layout.setVerticalSpacing(5)
        facts_layout.addWidget(section_header("ПАРАМЕТРЫ", "READ-ONLY", facts_panel), 0, 0, 1, 2)
        for row, label in enumerate(
            ("Здоровье", "Выносливость", "Радиация", "Ранг", "Репутация", "Карма"),
            start=1,
        ):
            value = QLabel("—", facts_panel)
            value.setObjectName("characterUnavailableValue")
            facts_layout.addWidget(QLabel(label, facts_panel), row, 0)
            facts_layout.addWidget(value, row, 1)
        profile_layout.addWidget(facts_panel)
        facts_note = QLabel(
            "Эти поля не извлечены текущим X-Ray snapshot и оставлены read-only.",
            profile,
        )
        facts_note.setObjectName("characterFactsNote")
        facts_note.setWordWrap(True)
        profile_layout.addWidget(facts_note)
        profile_layout.addStretch(1)
        workspace.addWidget(profile, 34)

        relations = panel(self, object_name="characterRelationsPanel")
        relations_layout = QVBoxLayout(relations)
        relations_layout.setContentsMargins(12, 12, 12, 12)
        relations_layout.addWidget(section_header("ОТНОШЕНИЕ К ГРУППИРОВКАМ", "GOODWILL", relations))
        self.faction_table = QTableWidget(0, 4, relations)
        self.faction_table.setObjectName("characterFactionTable")
        self.faction_table.setHorizontalHeaderLabels(("ГРУППИРОВКА", "ТЕКУЩЕЕ", "НОВОЕ", "СТАТУС"))
        self.faction_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.faction_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.faction_table.setShowGrid(False)
        self.faction_table.verticalHeader().setVisible(False)
        self.faction_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.faction_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        relations_layout.addWidget(self.faction_table, 1)
        self.warning_label = QLabel("Изменения отношений экспериментальны; backup обязателен.", relations)
        self.warning_label.setObjectName("characterWarning")
        self.warning_label.setWordWrap(True)
        relations_layout.addWidget(self.warning_label)
        # Controller-facing status surface; this is part of the canonical
        # character page, not a legacy faction widget.
        self.status_label = self.warning_label
        workspace.addWidget(relations, 66)
        workspace_host = QWidget(self)
        workspace_host.setObjectName("characterWorkspace")
        workspace_host.setLayout(workspace)
        body.addWidget(workspace_host, 1)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        self.back_button = action_button("НАЗАД К РЕДАКТОРУ", self)
        self.back_button.clicked.connect(self.back_requested)
        footer.addWidget(self.back_button)
        footer.addStretch(1)
        root.addLayout(footer)

    def set_snapshot(self, snapshot: Any) -> None:
        self.snapshot = snapshot
        release = str(getattr(snapshot, "release_id", "") or getattr(snapshot, "format_id", "")).casefold()
        capabilities = getattr(snapshot, "capabilities", None)
        self.editable = bool(
            is_xray_original_release(release)
            and snapshot.game_catalog is not None
            and capabilities is not None
            and getattr(capabilities, "edit_relations", False)
        )
        info = snapshot.info
        self.profile_label.setText(
            f"Релиз: {getattr(snapshot, 'format_title', release)}\n"
            f"Файл: {snapshot.path.name}\n"
            f"Целостность: {'CRC PASS' if info.crc_ok else 'проверить'}"
        )
        self.status_chip.setText("РЕДАКТИРУЕМЫЙ" if self.editable else "READ-ONLY")
        self._render_factions()

    def set_state(self, staged_relations: Mapping[str, int] | None = None, player_faction: str | None = None) -> None:
        self._staged = staged_relations or {}
        if player_faction is not None:
            index = self.player_faction_combo.findData(player_faction)
            if index >= 0:
                self.player_faction_combo.setCurrentIndex(index)
        self._render_factions()

    def _render_factions(self) -> None:
        snapshot = self.snapshot
        self.faction_table.setRowCount(0)
        self.player_faction_combo.clear()
        if snapshot is None or snapshot.game_catalog is None:
            self.player_faction_label.setText("Группировка: неизвестно")
            self.player_faction_combo.setEnabled(False)
            self.player_faction_button.setEnabled(False)
            self.faction_table.insertRow(0)
            self.faction_table.setItem(0, 0, QTableWidgetItem("Официальный каталог не найден"))
            return
        catalog = snapshot.game_catalog.factions
        info = snapshot.info
        definitions = [faction for faction in catalog.factions if faction.numeric_id is not None]
        current = dict(info.faction_relations)
        min_value = int(getattr(catalog, "goodwill_min", -2_147_483_648) or -2_147_483_648)
        max_value = int(getattr(catalog, "goodwill_max", 2_147_483_647) or 2_147_483_647)
        for faction in definitions:
            row = self.faction_table.rowCount()
            self.faction_table.insertRow(row)
            name = faction.display_name or faction.key
            self.faction_table.setItem(row, 0, QTableWidgetItem(name))
            has_current_value = faction.numeric_id in current
            current_value = current.get(faction.numeric_id, 0)
            self.faction_table.setItem(
                row,
                1,
                QTableWidgetItem(str(current_value) if has_current_value else "—"),
            )
            staged = self._staged.get(faction.key, current_value)
            if self.editable:
                spin = QSpinBox(self.faction_table)
                spin.setRange(min_value, max_value)
                spin.setValue(staged)
                self.faction_table.setCellWidget(row, 2, spin)
                stage_button = action_button(
                    "ИЗМЕНЕНО" if faction.key in self._staged else "ИЗМЕНИТЬ",
                    self.faction_table,
                )
                stage_button.clicked.connect(
                    lambda _checked=False, key=faction.key, editor=spin: self.relation_stage_requested.emit(
                        key, editor.value()
                    )
                )
                self.faction_table.setCellWidget(row, 3, stage_button)
            else:
                self.faction_table.setItem(row, 2, QTableWidgetItem(str(staged)))
                self.faction_table.setItem(row, 3, QTableWidgetItem("Только чтение"))
        for faction in definitions:
            self.player_faction_combo.addItem(faction.display_name or faction.key, faction.key)
        self.player_faction_combo.setEnabled(self.editable and bool(definitions))
        self.player_faction_button.setEnabled(self.editable and bool(definitions))

    def _stage_player_faction(self) -> None:
        index = self.player_faction_combo.currentIndex()
        if index >= 0:
            self.player_faction_stage_requested.emit(str(self.player_faction_combo.itemData(index) or self.player_faction_combo.currentText()))


__all__ = ["CharacterView"]
