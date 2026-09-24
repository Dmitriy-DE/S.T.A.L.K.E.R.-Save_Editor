"""Build small non-interactive textures for the canonical Qt shell.

Only the unoccupied environmental strip in the supplied canonical header is
sampled. All selected-surface and amber-button textures are generated locally;
no screenshot panel or interactive control is used as an application surface.
"""

from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tools" / "ui_review" / "references" / "01_LIBRARY_CANONICAL.png"
ASSETS = ROOT / "assets" / "ui" / "s2_shell"


def _paper_texture(path: Path, *, base: tuple[int, int, int], seed: int, amber: bool = False) -> None:
    rng = random.Random(seed)
    image = QImage(128, 128, QImage.Format.Format_RGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            grain = rng.randint(-8, 8)
            image.setPixelColor(
                x,
                y,
                QColor(*(max(0, min(255, component + grain)) for component in base)),
            )
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    speck_colors = (
        (73, 63, 42, 54),
        (48, 42, 27, 42),
        (255, 248, 219, 68),
    ) if amber else (
        (94, 83, 58, 58),
        (74, 68, 52, 44),
        (255, 250, 230, 72),
    )
    for _ in range(440 if amber else 650):
        red, green, blue, alpha = rng.choice(speck_colors)
        painter.setPen(QPen(QColor(red, green, blue, alpha), rng.choice((1, 1, 2))))
        x, y = rng.randrange(128), rng.randrange(128)
        painter.drawPoint(x, y)
        if rng.random() < 0.18:
            painter.drawLine(x, y, (x + rng.randrange(2, 9)) % 128, y)
    painter.end()
    # Match opposite edges so the tile repeats without a visible hard seam.
    for x in range(128):
        edge = image.pixelColor(x, 0)
        image.setPixelColor(x, 127, edge)
    for y in range(128):
        edge = image.pixelColor(0, y)
        image.setPixelColor(127, y, edge)
    image.save(str(path))


def _header_texture(path: Path) -> None:
    reference = QImage(str(REFERENCE))
    if reference.isNull():
        raise SystemExit(f"canonical header reference is missing: {REFERENCE}")
    image = QImage(1586, 122, QImage.Format.Format_RGB32)
    image.fill(QColor("#090c0b"))
    painter = QPainter(image)
    top_band = reference.copy(QRect(548, 0, 918, 73))
    painter.drawImage(QRect(548, 0, 918, 73), top_band)
    lower = QLinearGradient(0, 73, 0, 122)
    lower.setColorAt(0.0, QColor("#161b18"))
    lower.setColorAt(1.0, QColor("#080a09"))
    painter.fillRect(QRect(548, 73, 1038, 49), lower)
    painter.setPen(QColor("#33382f"))
    painter.drawLine(0, 121, 1585, 121)
    painter.end()
    image.save(str(path))


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    _header_texture(ASSETS / "header_panorama.png")
    _paper_texture(
        ASSETS / "selection_paper.png",
        base=(201, 194, 178),
        seed=0x51A7E,
    )
    _paper_texture(
        ASSETS / "amber_paper.png",
        base=(231, 181, 48),
        seed=0xA6B3,
        amber=True,
    )


if __name__ == "__main__":
    main()
