"""Real in-game previews and readable titles for library rows.

X-Ray games write a ``<save>.dds`` screenshot beside every ``.sav``;
S.T.A.L.K.E.R. 2 keeps a JPEG per slot under ``SaveGames/Thumbnails`` and the
region and play time in ``CampaignsSave.sav``.  Everything here is read-only
and optional: a missing preview falls back to the decorative artwork.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage

from editor.i18n import tr
from editor.s2_campaigns import region_slug, slot_meta, thumbnail_jpeg

from .xray_assets import decode_dds

_MAX_DDS_BYTES = 8 * 1024 * 1024
_IMAGE_CACHE: dict[tuple[Path, int], QImage | None] = {}

# Region keys observed in real S.T.A.L.K.E.R. 2 campaign indexes.
S2_REGION_NAMES: dict[str, str] = {
    "lesser_zone": "Малая Зона",
    "garbage": "Свалка",
    "zaton": "Затон",
    "swamp": "Болота",
    "sircaa": "НИИЧАЗ",
    "wild_island": "Дикий остров",
    "duga": "Дуга",
    "yantar": "Янтарь",
    "rostok": "Росток",
    "malachite": "Малахит",
    "red_forest": "Рыжий лес",
    "yanov": "Янов",
    "iron_forest": "Железный лес",
    "zalissya": "Залесье",
    "cement_factory": "Цементный завод",
    "chemical_plant": "Химзавод",
    "pripyat": "Припять",
    "chnpp": "ЧАЭС",
    "cnpp": "ЧАЭС",
    "cordon": "Кордон",
}


def s2_region_name(region_key: str) -> str:
    slug = region_slug(region_key)
    known = S2_REGION_NAMES.get(slug)
    return tr(known) if known else slug.replace("_", " ").capitalize()


def s2_row_text(path: Path) -> tuple[str, str] | None:
    """Return (title, subtitle) for an S2 slot, e.g. ("Янов", "22 ч в игре")."""

    meta = slot_meta(path)
    if meta is None:
        return None
    hours = tr("{0} ч в игре", int(meta.play_hours))
    suffix = path.stem[32:].strip("-_ ")
    return s2_region_name(meta.region_key), f"{hours} · {suffix}" if suffix else hours


def _load(path: Path, s2: bool) -> QImage | None:
    if s2:
        data = thumbnail_jpeg(path)
        if data is None:
            return None
        image = QImage.fromData(data)
        return None if image.isNull() else image
    dds = path.with_suffix(".dds")
    try:
        if dds.stat().st_size > _MAX_DDS_BYTES:
            return None
        image = decode_dds(dds.read_bytes())
    except (OSError, ValueError):
        return None
    return None if image.isNull() else image


def save_preview(path: Path, family: str | None) -> QImage | None:
    """Return the game's own screenshot for a save slot, cached by mtime."""

    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return None
    key = (path, stamp)
    if key not in _IMAGE_CACHE:
        _IMAGE_CACHE[key] = _load(path, str(family or "").startswith("stalker2"))
    return _IMAGE_CACHE[key]


__all__ = ["S2_REGION_NAMES", "s2_region_name", "s2_row_text", "save_preview"]
