"""Small, dependency-free Qt theme for the Zone inspired desktop shell.

The palette is kept in this module so the visual layer can evolve without
leaking presentation rules into the parser or editor service.  It uses only
Qt's built-in Fusion style and a stylesheet; no fonts, icons, or network
assets are required at runtime.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


COLORS = {
    "bg_base": "#111516",
    "bg_panel": "#1B2220",
    "bg_elevated": "#252D29",
    "bg_hover": "#2D3732",
    "border_subtle": "#2A3530",
    "border": "#39443D",
    "border_focus": "#A5B56B",
    "olive": "#A5B56B",
    "olive_dim": "#798647",
    "rust": "#B86442",
    "warning": "#D4A64B",
    "error": "#B95246",
    "success": "#6CA369",
    "text": "#E4E8DC",
    "text_secondary": "#929D94",
    "text_disabled": "#546058",
}


def stylesheet() -> str:
    """Return the complete application stylesheet."""

    c = COLORS
    return f"""
    QWidget {{
        background: {c['bg_base']};
        color: {c['text']};
        font-family: "Segoe UI", "Noto Sans", sans-serif;
        font-size: 13px;
    }}
    QMainWindow, QWidget#appRoot {{ background: {c['bg_base']}; }}
    QFrame#titleBar {{
        background: {c['bg_panel']};
        border-bottom: 1px solid {c['border']};
    }}
    QLabel#appTitle {{
        background: transparent;
        color: {c['text']};
        font-size: 18px;
        font-weight: 700;
        letter-spacing: 0.4px;
    }}
    QLabel#versionBadge, QLabel#sourceBadge, QLabel#integrityBadge,
    QLabel#formatBadge {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        color: {c['text_secondary']};
        padding: 4px 8px;
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#versionBadge {{ color: {c['olive']}; border-color: {c['olive_dim']}; }}
    QLabel#sourceBadge {{ color: {c['olive']}; }}
    QLabel#integrityBadge {{ color: {c['success']}; }}
    QLabel#formatBadge {{ color: {c['text_secondary']}; }}
    QFrame#metaBar {{
        background: {c['bg_panel']};
        border-bottom: 1px solid {c['border_subtle']};
    }}
    QLabel#metaFilename {{
        background: transparent;
        color: {c['text']};
        font-size: 14px;
        font-weight: 600;
    }}
    QLabel#metaDetails, QLabel#sourceLabel {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 11px;
    }}
    QFrame#sidebar {{
        background: {c['bg_panel']};
        border: 1px solid {c['border_subtle']};
        border-radius: 6px;
    }}
    QLabel#sidebarHeading, QLabel#sidebarStatus {{
        background: transparent;
        color: {c['text_secondary']};
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 10px;
        letter-spacing: 0.5px;
    }}
    QLabel#sidebarHeading {{ color: {c['olive']}; font-weight: 700; }}
    QPushButton#navButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        color: {c['text_secondary']};
        padding: 9px 10px;
        text-align: left;
    }}
    QPushButton#navButton:hover {{
        background: {c['bg_hover']};
        color: {c['text']};
        border-color: {c['border']};
    }}
    QPushButton#navButton:checked {{
        background: {c['bg_elevated']};
        border-color: {c['olive_dim']};
        color: {c['olive']};
        font-weight: 600;
    }}
    QFrame#contentPanel {{
        background: {c['bg_panel']};
        border: 1px solid {c['border_subtle']};
        border-radius: 6px;
    }}
    QTabWidget::pane {{
        background: {c['bg_panel']};
        border: none;
    }}
    QFrame#metricCard {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border']};
        border-radius: 5px;
    }}
    QLabel#metricCaption {{
        background: transparent;
        color: {c['text_secondary']};
        font-size: 11px;
        text-transform: uppercase;
    }}
    QLabel#metricValue {{
        background: transparent;
        color: {c['text']};
        font-family: "JetBrains Mono", "Cascadia Mono", monospace;
        font-size: 19px;
        font-weight: 700;
    }}
    QGroupBox {{
        background: {c['bg_panel']};
        border: 1px solid {c['border_subtle']};
        border-radius: 5px;
        margin-top: 12px;
        padding: 12px 10px 8px 10px;
    }}
    QGroupBox::title {{
        background: {c['bg_panel']};
        color: {c['olive']};
        left: 10px;
        padding: 0 5px;
    }}
    QLabel#statusLabel {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border_subtle']};
        border-radius: 4px;
        color: {c['text_secondary']};
        padding: 6px 9px;
    }}
    QLabel#errorLabel {{
        background: #2A1B1A;
        border: 1px solid {c['error']};
        border-radius: 4px;
        color: #F0B0A4;
        padding: 7px 9px;
    }}
    QPushButton {{
        background: {c['bg_elevated']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        color: {c['text']};
        padding: 7px 12px;
    }}
    QPushButton:hover {{ background: {c['bg_hover']}; border-color: {c['border_focus']}; }}
    QPushButton:pressed {{ background: {c['olive_dim']}; color: {c['bg_base']}; }}
    QPushButton:disabled {{ background: {c['bg_panel']}; color: {c['text_disabled']}; border-color: {c['border_subtle']}; }}
    QLineEdit, QSpinBox, QComboBox {{
        background: {c['bg_base']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        color: {c['text']};
        padding: 6px 8px;
        selection-background-color: {c['olive_dim']};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {c['border_focus']}; }}
    QTableView, QTableWidget, QListView {{
        background: {c['bg_base']};
        alternate-background-color: {c['bg_panel']};
        border: 1px solid {c['border_subtle']};
        gridline-color: {c['border_subtle']};
        selection-background-color: {c['olive_dim']};
        selection-color: {c['text']};
    }}
    QHeaderView::section {{
        background: {c['bg_elevated']};
        border: none;
        border-bottom: 1px solid {c['border']};
        color: {c['text_secondary']};
        font-size: 11px;
        font-weight: 600;
        padding: 7px 6px;
    }}
    QScrollBar:vertical {{ background: {c['bg_panel']}; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['olive_dim']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QProgressBar {{
        background: {c['bg_base']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        color: {c['text']};
        text-align: center;
    }}
    QProgressBar::chunk {{ background: {c['olive_dim']}; border-radius: 3px; }}
    QToolTip {{ background: {c['bg_elevated']}; border: 1px solid {c['border_focus']}; color: {c['text']}; }}
    """


def apply_theme(app: QApplication | None) -> None:
    """Apply the Zone palette to an existing QApplication instance."""

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
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["olive_dim"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(COLORS["text"]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet())


__all__ = ["COLORS", "apply_theme", "stylesheet"]
