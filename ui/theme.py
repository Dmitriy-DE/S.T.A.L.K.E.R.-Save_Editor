"""A restrained X-Ray-inspired theme for the desktop editor.

The reference mod uses the original game's metal panels, amber labels and
condensed lettering. Those game-owned textures are not redistributed here;
the same visual language is reproduced with Qt gradients and borders, while
official icon atlases are read locally by :mod:`ui.xray_assets` when present.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

COLORS = {
    # Keep the established base token so older shell integrations remain
    # compatible; the rest of the palette moves the UI into X-Ray's steel,
    # soot and amber range.
    "bg_base": "#111516",
    "bg_panel": "#1A2022",
    "bg_elevated": "#272A2B",
    "bg_hover": "#3A3934",
    "metal_light": "#57534B",
    "metal_dark": "#202426",
    "border_subtle": "#353A3B",
    "border": "#625C50",
    "border_focus": "#D6B34E",
    "amber": "#E4C354",
    "amber_bright": "#F3D77A",
    "amber_dim": "#9D8235",
    "rust": "#9B5D42",
    "warning": "#D8A54A",
    "error": "#B95D4B",
    "success": "#8AA367",
    "text": "#E7DFCF",
    "text_secondary": "#A39C8D",
    "text_disabled": "#5D615C",
}


def stylesheet() -> str:
    """Return the complete STALKER-style application stylesheet."""

    c = COLORS
    return f"""
    QWidget {{
        background: {c['bg_base']};
        color: {c['text']};
        font-family: "DejaVu Sans Condensed", "Liberation Sans Narrow", sans-serif;
        font-size: 13px;
    }}
    QMainWindow, QWidget#appRoot {{ background: {c['bg_base']}; }}
    QFrame#titleBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c['metal_light']}, stop:0.08 {c['bg_elevated']},
            stop:0.55 {c['metal_dark']}, stop:1 {c['bg_panel']});
        border-top: 1px solid {c['metal_light']};
        border-bottom: 2px solid {c['border']};
    }}
    QLabel#appTitle {{
        background: transparent;
        color: {c['amber_bright']};
        font-family: "DejaVu Sans Condensed", sans-serif;
        font-size: 20px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QLabel#versionBadge, QLabel#sourceBadge, QLabel#integrityBadge,
    QLabel#formatBadge {{
        background: {c['metal_dark']};
        border: 1px solid {c['border']};
        border-radius: 1px;
        color: {c['text_secondary']};
        padding: 4px 8px;
        font-family: "DejaVu Sans Mono", monospace;
        font-size: 10px;
        font-weight: 700;
    }}
    QLabel#versionBadge {{ color: {c['amber']}; border-color: {c['amber_dim']}; }}
    QLabel#sourceBadge {{ color: {c['amber']}; }}
    QLabel#integrityBadge {{ color: {c['success']}; }}
    QLabel#formatBadge {{ color: {c['text_secondary']}; }}
    QFrame#metaBar {{
        background: {c['bg_panel']};
        border-bottom: 1px solid {c['border_subtle']};
    }}
    QLabel#metaFilename {{
        background: transparent;
        color: {c['amber_bright']};
        font-size: 15px;
        font-weight: 700;
    }}
    QLabel#metaDetails, QLabel#sourceLabel {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: "DejaVu Sans Mono", monospace;
        font-size: 10px;
    }}
    QFrame#sidebar, QFrame#contentPanel {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c['bg_elevated']}, stop:0.35 {c['bg_panel']},
            stop:1 {c['metal_dark']});
        border: 1px solid {c['border']};
        border-radius: 1px;
    }}
    QLabel#sidebarHeading, QLabel#sidebarStatus {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: "DejaVu Sans Mono", monospace;
        font-size: 10px;
        letter-spacing: 1px;
    }}
    QLabel#sidebarHeading {{ color: {c['amber']}; font-weight: 700; }}
    QPushButton#navButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c['bg_elevated']}, stop:1 {c['metal_dark']});
        border: 1px solid {c['border_subtle']};
        border-left: 3px solid transparent;
        border-radius: 0px;
        color: {c['text_secondary']};
        padding: 9px 10px;
        text-align: left;
    }}
    QPushButton#navButton:hover {{
        background: {c['bg_hover']};
        color: {c['amber_bright']};
        border-color: {c['border']};
    }}
    QPushButton#navButton:checked {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c['amber_dim']}, stop:0.03 {c['bg_hover']}, stop:1 {c['metal_dark']});
        border-color: {c['border']};
        border-left-color: {c['amber']};
        color: {c['amber_bright']};
        font-weight: 700;
    }}
    QTabWidget::pane {{ background: {c['bg_panel']}; border: none; }}
    QFrame#metricCard {{
        background: {c['metal_dark']};
        border: 1px solid {c['border_subtle']};
        border-radius: 1px;
    }}
    QLabel#metricCaption {{
        background: transparent;
        color: {c['text_secondary']};
        font-size: 10px;
        letter-spacing: 1px;
    }}
    QLabel#metricValue {{
        background: transparent;
        color: {c['amber_bright']};
        font-family: "DejaVu Sans Mono", monospace;
        font-size: 19px;
        font-weight: 700;
    }}
    QGroupBox {{
        background: {c['bg_panel']};
        border: 1px solid {c['border']};
        border-radius: 1px;
        margin-top: 13px;
        padding: 12px 10px 8px 10px;
    }}
    QGroupBox::title {{
        background: {c['bg_panel']};
        color: {c['amber']};
        left: 10px;
        padding: 0 6px;
        font-weight: 700;
    }}
    QLabel#statusLabel {{
        background: {c['metal_dark']};
        border: 1px solid {c['border_subtle']};
        border-radius: 1px;
        color: {c['text_secondary']};
        padding: 6px 9px;
    }}
    QLabel#errorLabel {{
        background: #2E1D1A;
        border: 1px solid {c['error']};
        border-radius: 1px;
        color: #F0B0A4;
        padding: 7px 9px;
    }}
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c['metal_light']}, stop:0.12 {c['bg_elevated']},
            stop:1 {c['metal_dark']});
        border: 1px solid {c['border']};
        border-radius: 0px;
        color: {c['text']};
        padding: 7px 12px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background: {c['bg_hover']}; border-color: {c['border_focus']}; color: {c['amber_bright']}; }}
    QPushButton:pressed {{ background: {c['amber_dim']}; color: {c['bg_base']}; }}
    QPushButton:disabled {{ background: {c['bg_panel']}; color: {c['text_disabled']}; border-color: {c['border_subtle']}; }}
    QPushButton#supportButton {{
        background: transparent;
        border-color: {c['amber_dim']};
        color: {c['amber']};
        padding: 5px 9px;
        font-size: 11px;
    }}
    QPushButton#supportButton:hover {{ background: {c['bg_hover']}; color: {c['amber_bright']}; }}
    QDialog#supportDialog {{
        background: {c['bg_panel']};
        border: 1px solid {c['border']};
    }}
    QLabel#supportTitle {{
        background: transparent;
        color: {c['amber_bright']};
        font-size: 18px;
        font-weight: 700;
    }}
    QLabel#supportIntro, QLabel#supportDetail {{
        background: transparent;
        color: {c['text_secondary']};
    }}
    QLabel#supportMethod {{
        background: transparent;
        color: {c['amber']};
        font-weight: 700;
        margin-top: 3px;
    }}
    QLineEdit#supportValue {{
        background: #101416;
        color: {c['text']};
        font-family: "DejaVu Sans Mono", monospace;
        font-size: 11px;
    }}
    QPushButton#supportCopyButton, QPushButton#supportCloseButton {{
        padding: 5px 10px;
        min-width: 58px;
    }}
    QLineEdit, QSpinBox, QComboBox {{
        background: #101416;
        border: 1px solid {c['border']};
        border-radius: 0px;
        color: {c['text']};
        padding: 6px 8px;
        selection-background-color: {c['amber_dim']};
        selection-color: {c['bg_base']};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {c['border_focus']}; }}
    QComboBox QAbstractItemView {{
        background: {c['bg_panel']};
        border: 1px solid {c['border']};
        selection-background-color: {c['amber_dim']};
        selection-color: {c['bg_base']};
    }}
    QTableView, QTableWidget, QListView {{
        background: #101416;
        alternate-background-color: #181D1E;
        border: 1px solid {c['border']};
        gridline-color: #2A3030;
        selection-background-color: #635536;
        selection-color: {c['amber_bright']};
    }}
    QHeaderView::section {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c['metal_light']}, stop:1 {c['metal_dark']});
        border: none;
        border-right: 1px solid {c['border_subtle']};
        border-bottom: 1px solid {c['border']};
        color: {c['amber']};
        font-size: 10px;
        font-weight: 700;
        padding: 7px 6px;
    }}
    QScrollBar:vertical, QScrollBar:horizontal {{ background: {c['bg_panel']}; border: none; }}
    QScrollBar:vertical {{ width: 11px; margin: 0; }}
    QScrollBar:horizontal {{ height: 11px; margin: 0; }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {c['border']}; min-height: 24px; min-width: 24px; }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {c['amber_dim']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; height: 0; }}
    QProgressBar {{
        background: {c['bg_base']};
        border: 1px solid {c['border']};
        border-radius: 0px;
        color: {c['text']};
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {c['amber_dim']}; }}
    QToolTip {{ background: {c['bg_elevated']}; border: 1px solid {c['border_focus']}; color: {c['text']}; }}
    """


def apply_theme(app: QApplication | None) -> None:
    """Apply the X-Ray palette to an existing QApplication instance."""

    if app is None:
        return
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["bg_base"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["bg_base"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLORS["bg_panel"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS["bg_elevated"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["amber_dim"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS["bg_base"]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet())


__all__ = ["COLORS", "apply_theme", "stylesheet"]
