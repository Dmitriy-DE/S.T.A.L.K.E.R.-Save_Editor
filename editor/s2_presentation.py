"""Readable labels for S.T.A.L.K.E.R. 2 save-local item names.

Kept for callers that only need a label; :mod:`editor.s2_names` holds the
naming rules.  The parser itself keeps the raw SID in ``display_name``.
"""

from __future__ import annotations

from .s2_names import s2_readable_name


def s2_presentation_name(value: str | None) -> str | None:
    """Return a human label for a save-local S2 name."""

    return s2_readable_name(value)


__all__ = ["s2_presentation_name"]
