"""Packaged typography used by the canonical desktop and browser shells."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase

_SOURCE_FONT_ROOT = Path(__file__).resolve().parents[1] / "assets" / "fonts"
REFERENCE_FONT_NAMES = (
    "LiberationSansNarrow-Regular.ttf",
    "LiberationSansNarrow-Bold.ttf",
)
REFERENCE_FONT_FILES = tuple(_SOURCE_FONT_ROOT / name for name in REFERENCE_FONT_NAMES)
REFERENCE_FONT_FAMILY = "Liberation Sans Narrow"


def _font_root() -> Path:
    """Resolve source-tree and PyInstaller asset roots consistently."""

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled = Path(bundle_root) / "assets" / "fonts"
        if bundled.is_dir():
            return bundled
    return _SOURCE_FONT_ROOT


def load_reference_fonts() -> str:
    """Load the deterministic UI font and return its registered family name.

    The files are shipped with the application, so the UI never silently
    changes geometry because a host machine happens to have another narrow
    font installed.  Calling this more than once is harmless: Qt returns the
    existing application-font registration for the same file.
    """

    family_names: list[str] = []
    for name in REFERENCE_FONT_NAMES:
        path = _font_root() / name
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        family_names.extend(QFontDatabase.applicationFontFamilies(font_id))
    if REFERENCE_FONT_FAMILY in family_names:
        return REFERENCE_FONT_FAMILY
    return next(
        (family for family in family_names if family),
        REFERENCE_FONT_FAMILY,
    )


__all__ = [
    "REFERENCE_FONT_FAMILY",
    "REFERENCE_FONT_FILES",
    "REFERENCE_FONT_NAMES",
    "load_reference_fonts",
]
