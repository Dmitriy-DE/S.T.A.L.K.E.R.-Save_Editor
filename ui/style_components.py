"""Small Qt primitives shared by the reference-style shell and screens."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from editor.i18n import tr

_SHELL_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "s2_shell"
_SHELL_ICONS = Path(__file__).resolve().parents[1] / "assets" / "ui" / "shell_icons"


class TextureFrame(QFrame):
    """Paint a restrained decorative texture beneath ordinary child widgets."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        asset: str,
        tiled: bool = False,
        overlay_alpha: int = 158,
        draw_border: bool = True,
        image_height_ratio: float = 1.0,
    ) -> None:
        super().__init__(parent)
        self._texture = QPixmap(str(_SHELL_ASSETS / asset))
        self._tiled = tiled
        self._overlay_alpha = overlay_alpha
        self._draw_border = draw_border
        self._image_height_ratio = max(0.0, min(1.0, image_height_ratio))

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._texture.isNull():
            return
        painter = QPainter(self)
        image_height = round(self.height() * self._image_height_ratio)
        if self._image_height_ratio < 1.0:
            painter.fillRect(self.rect(), QColor(9, 11, 10))
            painter.drawPixmap(QRect(0, 0, self.width(), image_height), self._texture)
        elif self._tiled:
            for y in range(0, self.height(), self._texture.height()):
                for x in range(0, self.width(), self._texture.width()):
                    painter.drawPixmap(x, y, self._texture)
        else:
            painter.drawPixmap(self.rect(), self._texture)
        painter.fillRect(self.rect(), QColor(7, 9, 8, self._overlay_alpha))
        if self._draw_border:
            painter.setPen(QColor(51, 56, 47, 210))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


def panel(parent: QWidget | None = None, *, object_name: str = "referencePanel") -> QFrame:
    frame = QFrame(parent)
    frame.setObjectName(object_name)
    return frame


def section_header(
    title: str,
    subtitle: str = "",
    parent: QWidget | None = None,
    *,
    icon_name: str | None = None,
) -> QWidget:
    frame = panel(parent, object_name="sectionHeader")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(12)
    if icon_name:
        icon = QLabel(frame)
        icon.setObjectName("sectionIcon")
        icon_path = _SHELL_ICONS / f"{icon_name}.svg"
        if icon_path.is_file():
            icon.setPixmap(QIcon(str(icon_path)).pixmap(QSize(18, 18)))
        icon.setFixedSize(18, 18)
        layout.addWidget(icon)
    heading = QLabel(title, frame)
    heading.setObjectName("sectionHeading")
    layout.addWidget(heading)
    if subtitle:
        note = QLabel(subtitle, frame)
        note.setObjectName("sectionNote")
        note.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(note, 1)
    else:
        layout.addStretch(1)
    return frame


def action_button(
    text: str,
    parent: QWidget | None = None,
    *,
    kind: str = "neutral",
    object_name: str | None = None,
) -> QPushButton:
    button = QPushButton(text, parent)
    button.setObjectName(object_name or f"{kind}Button")
    button.setProperty("buttonKind", kind)
    return button


def primary_button(text: str, parent: QWidget | None = None) -> QPushButton:
    """Create the amber action used for a committed user intent."""

    return action_button(text, parent, kind="primary", object_name="primaryButton")


def status_chip(
    text: str,
    parent: QWidget | None = None,
    *,
    tone: str = "neutral",
) -> QLabel:
    label = QLabel(text, parent)
    label.setObjectName("statusChip")
    label.setProperty("tone", tone)
    return label


def reference_game_rail(
    parent: QWidget | None = None,
    *,
    object_name: str = "referenceGameRail",
    active_family: str = "stalker2",
) -> QFrame:
    """Build the compact game rail shared by secondary canonical screens.

    The rail is presentation-only: it mirrors the official release registry
    and intentionally has no fake discovery counts or edit affordances.
    """

    rail = panel(parent, object_name=object_name)
    rail.setFixedWidth(246)
    layout = QVBoxLayout(rail)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)
    layout.addWidget(QLabel(tr("ИГРЫ"), rail), 0)
    rule = QFrame(rail)
    rule.setFrameShape(QFrame.Shape.HLine)
    rule.setObjectName("railRule")
    layout.addWidget(rule)
    games = QListWidget(rail)
    games.setObjectName("referenceSecondaryGameList")
    games.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
    games.setIconSize(QSize(22, 22))
    entries = (
        (tr("ВСЕ ИГРЫ"), tr("Локальные сохранения"), "all"),
        ("S.T.A.L.K.E.R. 2", "Heart of Chornobyl", "stalker2"),
        ("Call of Pripyat", "X-Ray original", "cop"),
        ("Clear Sky", "X-Ray original", "clear_sky"),
        ("Shadow of Chornobyl", "X-Ray original", "soc"),
    )
    selected_row = 0
    for row, (title, detail, family) in enumerate(entries):
        item = QListWidgetItem(f"{title}\n{detail}")
        icon_name = "game-grid.svg" if family == "all" else "radiation.svg"
        item.setIcon(QIcon(str(_SHELL_ICONS / icon_name)))
        item.setData(Qt.ItemDataRole.UserRole, family)
        item.setSizeHint(QSize(0, 60))
        games.addItem(item)
        if family == active_family:
            selected_row = row
    games.setCurrentRow(selected_row)
    # Display-only: it shows which game the screen is about.  Letting it take
    # clicks would suggest a filter that does not exist.
    games.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    games.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    layout.addWidget(games, 1)
    zone = TextureFrame(
        rail,
        asset="rail_zone.png",
        overlay_alpha=0,
        image_height_ratio=0.66,
    )
    zone.setObjectName("secondaryZoneDecoration")
    zone.setFixedHeight(294)
    zone_layout = QVBoxLayout(zone)
    zone_layout.setContentsMargins(12, 20, 12, 12)
    zone_layout.addStretch(1)
    note = QLabel(tr("ЗОНА НЕ ПРОЩАЕТ ОШИБОК.\nРЕЗЕРВНАЯ КОПИЯ\nПРОЩАЕТ."), zone)
    note.setObjectName("zoneDecorationText")
    note.setWordWrap(True)
    zone_layout.addWidget(note)
    layout.addWidget(zone)
    return rail


def select_rail_family(rail: QWidget, family: str | None) -> None:
    """Highlight one family (or "all") on a display-only game rail."""

    games = rail.findChild(QListWidget, "referenceSecondaryGameList")
    if games is None:
        return
    wanted = family or "all"
    for row in range(games.count()):
        if games.item(row).data(Qt.ItemDataRole.UserRole) == wanted:
            games.setCurrentRow(row)
            return


def key_hint(key: str, text: str, parent: QWidget | None = None) -> QWidget:
    frame = QWidget(parent)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    key_label = QLabel(key, frame)
    key_label.setObjectName("keyHintKey")
    label = QLabel(text, frame)
    label.setObjectName("keyHintText")
    layout.addWidget(key_label)
    layout.addWidget(label)
    return frame


__all__ = [
    "TextureFrame",
    "action_button",
    "key_hint",
    "panel",
    "primary_button",
    "reference_game_rail",
    "section_header",
    "select_rail_family",
    "status_chip",
]
