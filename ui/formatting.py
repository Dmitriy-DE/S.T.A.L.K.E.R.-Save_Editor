"""Small formatting helpers shared by the Qt views."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath


def human_size(size: int) -> str:
    """Format a byte count with the binary units used by the desktop UI."""

    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def human_money(value: int) -> str:
    """Use the grouped currency presentation from the canonical shell."""

    return f"{int(value):,}".replace(",", " ")


def currency_suffix(release_id: str | None) -> str:
    """S.T.A.L.K.E.R. 2 pays in coupons; the original trilogy uses roubles."""

    return "куп." if str(release_id or "").casefold().startswith("stalker2") else "₽"


def plural_ru(count: int, one: str, few: str, many: str) -> str:
    """Pick the Russian plural form: 1 сохранение, 2 сохранения, 5 сохранений."""

    value = abs(int(count))
    if value % 10 == 1 and value % 100 != 11:
        return one
    if 2 <= value % 10 <= 4 and not 12 <= value % 100 <= 14:
        return few
    return many


def count_ru(count: int, one: str, few: str, many: str) -> str:
    return f"{count} {plural_ru(count, one, few, many)}"


_MONTHS_RU = ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
_BACKUP_SUFFIX_RE = re.compile(
    r"_\d{8}T\d{6,}Z_[0-9a-f]{32}_(?:ORIGINAL|EDITED)$", re.IGNORECASE
)


def human_datetime(value: datetime | str | None, *, now: datetime | None = None) -> str:
    """"Сегодня, 09:48" / "Вчера, 23:41" / "21 сен, 18:13" / "21 сен 2025, 18:13"."""

    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        text = value
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if value.tzinfo is not None:
        value = value.astimezone()
    current = now or datetime.now()
    today = current.date()
    # Never pass Cyrillic to strftime: on Windows it encodes the format with
    # the C locale and raises UnicodeEncodeError outside Russian locales.
    if value.date() == today:
        return f"Сегодня, {value:%H:%M}"
    if value.date() == today - timedelta(days=1):
        return f"Вчера, {value:%H:%M}"
    month = _MONTHS_RU[value.month - 1]
    year = "" if value.year == today.year else f" {value.year}"
    return f"{value.day:02d} {month}{year}, {value:%H:%M}"


def source_display_name(source_path: str | None, backup_path: Path | None = None) -> str:
    """Show a save's own file name, never a sanitised backup file name."""

    if source_path:
        name = PurePosixPath(str(source_path).replace("\\", "/")).name
        if name:
            return name
    if backup_path is not None:
        stem = _BACKUP_SUFFIX_RE.sub("", Path(backup_path).stem)
        # Cloud locators are flattened with "_" inside the backup name.
        return f"{stem.rsplit('_', 1)[-1] if stem.startswith('%') else stem}{Path(backup_path).suffix}"
    return "Неизвестный источник"


__all__ = [
    "count_ru",
    "currency_suffix",
    "human_datetime",
    "human_money",
    "human_size",
    "plural_ru",
    "source_display_name",
]
