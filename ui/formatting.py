"""Small formatting helpers shared by the Qt views."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from editor.i18n import tr, trn


def human_size(size: int) -> str:
    """Format a byte count with the binary units used by the desktop UI."""

    value = float(size)
    for unit in (tr("Б"), tr("КБ"), tr("МБ"), tr("ГБ")):
        if value < 1024 or unit == tr("ГБ"):
            return f"{value:.1f} {unit}" if unit != tr("Б") else tr("{0} Б", int(value))
        value /= 1024
    return tr("{0} Б", size)


def human_money(value: int) -> str:
    """Use the grouped currency presentation from the canonical shell."""

    return f"{int(value):,}".replace(",", " ")


def currency_suffix(release_id: str | None) -> str:
    """S.T.A.L.K.E.R. 2 pays in coupons; the original trilogy uses roubles."""

    return tr("куп.") if str(release_id or "").casefold().startswith("stalker2") else "₽"


def plural_ru(count: int, one: str, few: str, many: str) -> str:
    """Plural of a Russian source word in the UI language: 1 сохранение, 5 сохранений."""

    return trn(count, one, few, many)


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
        return tr("Сегодня, {0:%H:%M}", value)
    if value.date() == today - timedelta(days=1):
        return tr("Вчера, {0:%H:%M}", value)
    month = tr(_MONTHS_RU[value.month - 1])
    if value.year == today.year:
        return tr("{0:02d} {1}, {2:%H:%M}", value.day, month, value)
    return tr("{0:02d} {1} {2}, {3:%H:%M}", value.day, month, value.year, value)


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
    return tr("Неизвестный источник")


__all__ = [
    "count_ru",
    "currency_suffix",
    "human_datetime",
    "human_money",
    "human_size",
    "plural_ru",
    "source_display_name",
]
