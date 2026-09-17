#!/usr/bin/env python3
"""Extract real X-Ray UI chrome (frames, buttons) into a bundled skin pack.

Like the icon pack, this crops authentic pixels from the game's own
``ui_common`` control atlas so the editor's panels and buttons are drawn from
the same elements as the game, on both the desktop app and the website.  The
nine-slice frame and button-state textures are recomposed into standalone
PNGs that CSS ``border-image`` and Qt ``border-image`` can stretch.

Usage: python tools/build_chrome_pack.py [--source DIR] [--web]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ASSET_DIR = ROOT / "assets" / "chrome" / "xray"
WEB_DIR = ROOT / "web" / "chrome"

# Nine-slice frames: (output, prefix, corner) where the atlas holds
# <prefix>_lt/t/rt/l/back/r/lb/b/rb regions.
_FRAMES = {
    "frame": "ui_tablist_textbox",
    "frame_thin": "ui_stroketextbox",
}
# Button state textures cropped whole (horizontally stretchable ends).
_BUTTONS = {
    "button": "ui_button_ordinary_e",
    "button_hover": "ui_button_ordinary_h",
    "button_press": "ui_button_ordinary_t",
    "button_disabled": "ui_button_ordinary_d",
}


def _regions(xml: str) -> dict[str, tuple[int, int, int, int]]:
    out: dict[str, tuple[int, int, int, int]] = {}
    for m in re.finditer(
        r'id="([^"]+)"\s+x="(\d+)"\s+y="(\d+)"\s+width="(\d+)"\s+height="(\d+)"', xml
    ):
        out[m.group(1)] = tuple(int(m.group(i)) for i in range(2, 6))  # type: ignore[assignment]
    return out


def build(source: Path | None, *, mirror_web: bool) -> int:
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QGuiApplication, QImage, QPainter

    from editor.platforms import installed_releases
    from editor.xray_catalog import _read_xray_archive, read_xray_asset
    from ui.xray_assets import decode_dds

    QGuiApplication.instance() or QGuiApplication([])

    roots = [source] if source is not None else [
        Path(g.install_dir)
        for g in installed_releases()
        if g.release_id.endswith("-ee")
    ]
    atlas = None
    regions: dict[str, tuple[int, int, int, int]] = {}
    for root in roots:
        raw = read_xray_asset(root, "ui\\ui_common")
        if raw is None:
            continue
        atlas = decode_dds(raw)
        try:
            archive = _read_xray_archive(root / "resources" / "configs.db")
        except (OSError, ValueError):
            archive = {}
        for name, data in archive.items():
            if name.lower().endswith("ui_common.xml"):
                regions = _regions(data.decode("cp1251", "ignore"))
                break
        if atlas is not None and regions:
            break
    if atlas is None or not regions:
        print("no readable ui_common atlas found", file=sys.stderr)
        return 1

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    written = 0

    def crop(rid: str) -> QImage | None:
        box = regions.get(rid)
        if box is None:
            return None
        x, y, w, h = box
        piece = atlas.copy(QRect(x, y, w, h))
        return piece if not piece.isNull() else None

    # Recompose nine-slice frames into a single grid image for border-image.
    for out_name, prefix in _FRAMES.items():
        raw_parts = {p: crop(f"{prefix}_{p}") for p in
                     ("lt", "t", "rt", "l", "back", "r", "lb", "b", "rb")}
        if any(v is None for v in raw_parts.values()):
            continue
        parts = {k: v for k, v in raw_parts.items() if v is not None}
        c = parts["lt"].width()  # corner size (square regions)
        canvas = QImage(c * 3, c * 3, QImage.Format.Format_RGBA8888)
        canvas.fill(0)
        painter = QPainter(canvas)
        grid = [("lt", 0, 0), ("t", 1, 0), ("rt", 2, 0),
                ("l", 0, 1), ("back", 1, 1), ("r", 2, 1),
                ("lb", 0, 2), ("b", 1, 2), ("rb", 2, 2)]
        for key, gx, gy in grid:
            painter.drawImage(
                QRect(gx * c, gy * c, c, c), parts[key],
                QRect(0, 0, parts[key].width(), parts[key].height()),
            )
        painter.end()
        if canvas.save(str(ASSET_DIR / f"{out_name}.png")):
            written += 1
            print(f"  {out_name}.png  (slice={c})")

    for out_name, rid in _BUTTONS.items():
        piece = crop(rid)
        if piece is not None and piece.save(str(ASSET_DIR / f"{out_name}.png")):
            written += 1
            print(f"  {out_name}.png  ({piece.width()}x{piece.height()})")

    if mirror_web and written:
        WEB_DIR.mkdir(parents=True, exist_ok=True)
        for png in ASSET_DIR.glob("*.png"):
            shutil.copy2(png, WEB_DIR / png.name)

    print(f"chrome pack: {written} textures -> {ASSET_DIR.relative_to(ROOT)}")
    return 0 if written else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--web", action="store_true")
    args = parser.parse_args(argv)
    return build(args.source, mirror_web=args.web)


if __name__ == "__main__":
    raise SystemExit(main())
