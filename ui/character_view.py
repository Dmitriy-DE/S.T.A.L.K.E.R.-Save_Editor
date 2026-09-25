"""X-Ray character and faction state, shown only for supported releases."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from editor.i18n import tr
from editor.official_names import official_name
from editor.releases import is_xray_original_release, release_by_id

from .style_components import (
    action_button,
    panel,
    reference_game_rail,
    section_header,
    select_rail_family,
    status_chip,
)
from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import technical_details


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
        self._staged_player_faction: str | None = None
        self._details_dialog: TechnicalDetailsDialog | None = None
        self._technical_detail_text = ""
        self._diagnostic_detail_text = ""
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 20, 0, 0)
        root.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(QLabel(tr("ПЕРСОНАЖ И ГРУППИРОВКИ (X-RAY)"), self))
        self.status_chip = status_chip(tr("ТОЛЬКО X-RAY"), self, tone="neutral")
        heading.addStretch(1)
        heading.addWidget(self.status_chip)
        root.addLayout(heading)

        body = QHBoxLayout()
        body.setSpacing(10)
        self.game_rail = reference_game_rail(
            self,
            object_name="characterGameRail",
            active_family="cop",
        )
        body.addWidget(
            self.game_rail,
            0,
        )
        workspace = QHBoxLayout()
        workspace.setSpacing(10)
        profile = panel(self, object_name="characterProfilePanel")
        profile_layout = QVBoxLayout(profile)
        profile_layout.setContentsMargins(12, 12, 12, 12)
        profile_layout.addWidget(section_header(tr("ПЕРСОНАЖ"), tr("ДАННЫЕ ИГРОКА"), profile))
        self.profile_label = QLabel(tr("Сохранение не проанализировано"), profile)
        self.profile_label.setObjectName("characterProfileLabel")
        self.profile_label.setWordWrap(True)
        profile_layout.addWidget(self.profile_label)
        self.player_faction_label = QLabel(tr("Группировка: неизвестно"), profile)
        profile_layout.addWidget(self.player_faction_label)
        self.player_faction_combo = QComboBox(profile)
        self.player_faction_combo.setEnabled(False)
        profile_layout.addWidget(self.player_faction_combo)
        self.player_faction_button = action_button(tr("ИЗМЕНИТЬ"), profile)
        self.player_faction_button.setEnabled(False)
        self.player_faction_button.clicked.connect(self._stage_player_faction)
        profile_layout.addWidget(self.player_faction_button)
        # Read-only actor facts parsed from the X-Ray actor STATE; nothing
        # here is ever written back.
        self.actor_facts = QLabel("", profile)
        self.actor_facts.setObjectName("characterActorFacts")
        self.actor_facts.setWordWrap(True)
        self.actor_facts.setToolTip(tr("Только просмотр: эти значения прочитаны из сохранения и не изменяются."))
        profile_layout.addWidget(self.actor_facts)
        profile_layout.addStretch(1)
        workspace.addWidget(profile, 34)

        relations = panel(self, object_name="characterRelationsPanel")
        relations_layout = QVBoxLayout(relations)
        relations_layout.setContentsMargins(12, 12, 12, 12)
        relations_layout.addWidget(section_header(tr("ОТНОШЕНИЕ К ГРУППИРОВКАМ"), tr("ОТНОШЕНИЯ"), relations))
        self.faction_table = QTableWidget(0, 4, relations)
        self.faction_table.setObjectName("characterFactionTable")
        self.faction_table.setHorizontalHeaderLabels((tr("ГРУППИРОВКА"), tr("ТЕКУЩЕЕ"), tr("НОВОЕ"), tr("СТАТУС")))
        self.faction_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.faction_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.faction_table.setShowGrid(False)
        self.faction_table.verticalHeader().setVisible(False)
        self.faction_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.faction_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        relations_layout.addWidget(self.faction_table, 1)
        self.warning_label = QLabel(
            tr("Изменение отношений — экспериментальная функция. Перед сохранением будет создана резервная копия."),
            relations,
        )
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
        self.back_button = action_button(tr("НАЗАД К РЕДАКТОРУ"), self)
        self.back_button.clicked.connect(self.back_requested)
        footer.addWidget(self.back_button)
        self.details_button = action_button(tr("ТЕХНИЧЕСКИЕ ДЕТАЛИ"), self)
        self.details_button.setObjectName("characterTechnicalDetailsButton")
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self._show_technical_details)
        footer.addWidget(self.details_button)
        footer.addStretch(1)
        root.addLayout(footer)

    def set_snapshot(self, snapshot: Any) -> None:
        self.snapshot = snapshot
        self._diagnostic_detail_text = ""
        release = str(getattr(snapshot, "release_id", "") or getattr(snapshot, "format_id", "")).casefold()
        self._release_id = release
        try:
            select_rail_family(self.game_rail, release_by_id(release).family)
        except KeyError:
            select_rail_family(self.game_rail, None)
        capabilities = getattr(snapshot, "capabilities", None)
        self.editable = bool(
            is_xray_original_release(release)
            and snapshot.game_catalog is not None
            and capabilities is not None
            and getattr(capabilities, "edit_relations", False)
        )
        info = snapshot.info
        self.profile_label.setText(
            tr("Версия: {0}\nФайл: {1}\nПроверка: {2}", getattr(snapshot, 'format_title', None) or tr("Неизвестная версия"), snapshot.path.name, tr("Файл проверен") if info.crc_ok else tr("Файл повреждён или изменён"))
        )
        self.profile_label.setToolTip("")
        self._technical_detail_text = technical_details(
            tr("Идентификатор версии: {0}\nПуть к файлу: {1}\nSHA-256: {2}\nCRC: {3}", release, snapshot.path, info.sha256, 'PASS' if info.crc_ok else 'FAIL')
        )
        self.details_button.setVisible(True)
        self.status_chip.setText(tr("МОЖНО ИЗМЕНЯТЬ") if self.editable else tr("ТОЛЬКО ЧТЕНИЕ"))
        self.actor_facts.setText(actor_facts_text(info))
        self.actor_facts.setVisible(bool(self.actor_facts.text()))
        self._render_factions()

    def set_diagnostic_details(self, value: object) -> None:
        self._diagnostic_detail_text = technical_details(value)
        self.details_button.setVisible(
            bool(self._technical_detail_text or self._diagnostic_detail_text)
        )

    def set_state(self, staged_relations: Mapping[str, int] | None = None, player_faction: str | None = None) -> None:
        self._staged = staged_relations or {}
        self._staged_player_faction = player_faction
        self._render_factions()

    def _faction_label(self, faction) -> str:
        name = (
            official_name(getattr(self, "_release_id", None), "factions", faction.key)
            or faction.display_name
            or tr("Группировка {0}", faction.numeric_id)
        )
        # Clear Sky and SoC keep separate "actor_*" communities for the player;
        # without a marker they read as duplicates ("Бандит", "Бандит").
        if faction.key == "actor" or faction.key.startswith("actor_"):
            return tr("{0} (игрок)", name)
        return name

    def _render_factions(self) -> None:
        snapshot = self.snapshot
        self.faction_table.setRowCount(0)
        self.player_faction_combo.clear()
        if snapshot is None or snapshot.game_catalog is None:
            self.player_faction_label.setText(tr("Группировка: неизвестно"))
            self.player_faction_combo.setEnabled(False)
            self.player_faction_button.setEnabled(False)
            self.faction_table.insertRow(0)
            self.faction_table.setItem(
                0,
                0,
                QTableWidgetItem(tr("Данные о группировках недоступны для этого сохранения.")),
            )
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
            self.faction_table.setItem(row, 0, QTableWidgetItem(self._faction_label(faction)))
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
                    tr("ИЗМЕНЕНО") if faction.key in self._staged else tr("ИЗМЕНИТЬ"),
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
                self.faction_table.setItem(row, 3, QTableWidgetItem(tr("Только чтение")))
        current_player = next(
            (
                faction
                for faction in definitions
                if faction.numeric_id == info.player_faction_index
            ),
            None,
        )
        self.player_faction_label.setText(
            tr("Группировка игрока: {0}", self._faction_label(current_player))
            if current_player is not None
            else tr("Группировка игрока: не определена")
        )
        self.player_faction_combo.blockSignals(True)
        for faction in definitions:
            index = self.player_faction_combo.count()
            self.player_faction_combo.addItem(self._faction_label(faction), faction.key)
            if not faction.display_name:
                self.player_faction_combo.setItemData(index, "", Qt.ItemDataRole.ToolTipRole)
        wanted = self._staged_player_faction or (
            current_player.key if current_player is not None else None
        )
        if wanted is not None:
            index = self.player_faction_combo.findData(wanted)
            if index >= 0:
                self.player_faction_combo.setCurrentIndex(index)
        self.player_faction_combo.blockSignals(False)
        self.player_faction_combo.setEnabled(self.editable and bool(definitions))
        self.player_faction_button.setEnabled(self.editable and bool(definitions))

    def _show_technical_details(self) -> None:
        details = "\n".join(
            value
            for value in (self._technical_detail_text, self._diagnostic_detail_text)
            if value
        )
        if not details:
            return
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(details, self)
        self._details_dialog.open()

    def _stage_player_faction(self) -> None:
        index = self.player_faction_combo.currentIndex()
        if index >= 0:
            self.player_faction_stage_requested.emit(str(self.player_faction_combo.itemData(index) or self.player_faction_combo.currentText()))


__all__ = ["CharacterView"]


def actor_facts_text(info: Any) -> str:
    """Name, health, rating, reputation and in-game date, when the save has them."""

    lines: list[str] = []
    name = getattr(info, "actor_name", None)
    if name:
        lines.append(tr("Имя: {0}", name))
    health = getattr(info, "actor_health", None)
    if health is not None:
        lines.append(tr("Здоровье: {0}%", round(health * 100)))
    rank = getattr(info, "actor_rank", None)
    if rank is not None:
        lines.append(tr("Рейтинг: {0}", rank))
    reputation = getattr(info, "actor_reputation", None)
    if reputation is not None:
        lines.append(tr("Репутация: {0}", reputation))
    game_time = getattr(info, "game_time", None)
    if game_time:
        try:
            moment = datetime(1, 1, 1) + timedelta(milliseconds=int(game_time))
        except (OverflowError, ValueError):
            moment = None
        if moment is not None and 1990 <= moment.year <= 2100:
            lines.append(tr("Дата в игре: {0}", f"{moment:%d.%m.%Y %H:%M}"))
    return "\n".join(lines)
