"""Small formatting helpers shared by the Qt views."""

from __future__ import annotations


def human_size(size: int) -> str:
    """Format a byte count with the binary units used by the desktop UI."""

    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


__all__ = ["human_size"]
