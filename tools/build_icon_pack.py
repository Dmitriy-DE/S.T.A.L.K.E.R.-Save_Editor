#!/usr/bin/env python3
"""Extract real X-Ray inventory icons into a bundled pack.

The editor ships these cropped PNGs so inventory icons are always present in
the desktop app and on the website, without a game install at runtime.  The
source pixels come from the official ``ui_icon_equipment`` atlas of an
installed trilogy release (or one passed with ``--source``); each item that
declares atlas coordinates is cropped at native resolution and written to
``assets/icons/xray/<item-key>.png``.  Keys are shared across the trilogy, so
the union of every readable install gives the widest coverage.

Usage:
    python tools/build_icon_pack.py [--source DIR ...] [--web]

Without ``--source`` the tool discovers installed Steam releases.  ``--web``
also mirrors the pack into ``web/icons/`` so the static site can serve it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import sys
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ASSET_DIR = ROOT / "assets" / "icons" / "xray"
WEB_DIR = ROOT / "web" / "icons"
_CELL = 50

if TYPE_CHECKING:
    from PySide6.QtGui import QImage


_EDITIONS = frozenset({"original", "enhanced"})


def _catalogs(sources: list[Path]):
    """Yield trilogy catalogs, Enhanced Editions first."""

    from editor.platforms import installed_releases
    from editor.releases import official_releases, release_by_id
    from editor.xray_catalog import XRayCatalogProvider

    roots: list[Path] = list(sources)
    release_ids: list[str | None] = [None] * len(sources)
    if not sources:
        for game in installed_releases():
            roots.append(Path(game.install_dir))
            release_ids.append(game.release_id)

    catalogs = []
    for root, release_id in zip(roots, release_ids, strict=True):
        try:
            release = release_by_id(release_id) if release_id else None
        except KeyError:
            release = None
        candidates = [release] if release is not None else list(official_releases())
        for candidate in candidates:
            catalog = XRayCatalogProvider().load(
                candidate, root, allowed_editions=_EDITIONS
            )
            if catalog is not None and catalog.source_root is not None:
                catalogs.append(catalog)
                break

    # The 2025 Enhanced Editions keep the original 50 px atlas (checked:
    # ui_icon_equipment.dds is 1024x2048 DXT5 in all three), so this order
    # only decides which of two identical-resolution crops is kept.
    catalogs.sort(key=lambda cat: 0 if cat.release_id.endswith("-ee") else 1)
    yield from catalogs


def build(sources: list[Path], *, mirror_web: bool) -> int:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QGuiApplication

    from ui.xray_assets import XRayIconResolver, decode_dds

    app = QGuiApplication.instance() or QGuiApplication([])
    _ = app

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    atlas_cache: dict[tuple, QImage | None] = {}

    for catalog in _catalogs(sources):
        resolver = XRayIconResolver(catalog)
        source_root = catalog.source_root
        for definition in catalog.items:
            if definition.key in written:
                continue
            if definition.icon_x is None or definition.icon_y is None:
                continue
            texture = (definition.icon_texture or "ui_icon_equipment")
            cache_key = (source_root, texture)
            atlas = atlas_cache.get(cache_key)
            if cache_key not in atlas_cache:
                atlas = _load_atlas(resolver, source_root, texture, decode_dds)
                atlas_cache[cache_key] = atlas
            if atlas is None:
                continue
            width = max(1, definition.width or 1) * _CELL
            height = max(1, definition.height or 1) * _CELL
            x = definition.icon_x * _CELL
            y = definition.icon_y * _CELL
            if x >= atlas.width() or y >= atlas.height():
                continue
            crop = atlas.copy(QRect(x, y, width, height))
            if crop.isNull():
                continue
            out = ASSET_DIR / f"{definition.key}.png"
            if crop.save(str(out)):
                written[definition.key] = definition.category or "item"

    manifest = {"keys": sorted(written)}
    (ASSET_DIR / "index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=0), encoding="utf-8"
    )

    if mirror_web:
        WEB_DIR.mkdir(parents=True, exist_ok=True)
        for png in ASSET_DIR.glob("*.png"):
            shutil.copy2(png, WEB_DIR / png.name)
        shutil.copy2(ASSET_DIR / "index.json", WEB_DIR / "index.json")

    print(f"icon pack: {len(written)} icons -> {ASSET_DIR.relative_to(ROOT)}")
    if mirror_web:
        print(f"mirrored  -> {WEB_DIR.relative_to(ROOT)}")
    return 0


def _load_atlas(resolver, source_root: Path, texture: str, decode_dds) -> QImage | None:
    from editor.xray_catalog import read_xray_asset

    path = type(resolver)._atlas_path(source_root, texture)
    try:
        if path is not None:
            return decode_dds(path.read_bytes())
        raw = read_xray_asset(source_root, texture.replace("\\", "/"))
        return decode_dds(raw) if raw is not None else None
    except (OSError, ValueError, struct.error):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        type=Path,
        help="Install root or gamedata dir to extract from (repeatable).",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Also mirror the pack into web/icons/ for the static site.",
    )
    args = parser.parse_args(argv)
    return build(args.source, mirror_web=args.web)


if __name__ == "__main__":
    raise SystemExit(main())
