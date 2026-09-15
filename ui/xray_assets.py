"""Read-only X-Ray atlas access for the desktop inventory view.

The editor never bundles GSC or mod textures.  When an official installation
has an unpacked ``gamedata`` tree, this module reads its own icon atlas and
returns cropped ``QIcon`` objects in memory.  Packed installs and unavailable
atlases use small repository-owned category glyphs instead of pretending that
an icon was found.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap

from editor.catalog import ItemCatalog, ItemDefinition
from editor.xray_catalog import read_xray_asset

_DDS_HEADER_SIZE = 128
_ICON_CELL_SIZE = 50
_RGBA_FORMAT = QImage.Format.Format_RGBA8888
_CATEGORY_COLORS = {
    "ammo": QColor("#e5c36a"),
    "weapon": QColor("#d99b62"),
    "outfit": QColor("#aeb9a8"),
    "artifact": QColor("#7fc0b5"),
    "consumable": QColor("#d58b73"),
    "grenade": QColor("#b5ad78"),
    "item": QColor("#c0b9a6"),
}


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _channel(value: int, mask: int) -> int:
    if not mask:
        return 0
    shift = (mask & -mask).bit_length() - 1
    width = mask.bit_count()
    raw = (value & mask) >> shift
    maximum = (1 << width) - 1
    return (raw * 255 + maximum // 2) // maximum


def _rgb565(value: int) -> tuple[int, int, int]:
    return (
        ((value >> 11) & 0x1F) * 255 // 31,
        ((value >> 5) & 0x3F) * 255 // 63,
        (value & 0x1F) * 255 // 31,
    )


def _dxt_colors(block: bytes, *, allow_transparent: bool) -> tuple[tuple[int, int, int, int], ...]:
    first, second = struct.unpack_from("<HH", block, 0)
    c0 = _rgb565(first)
    c1 = _rgb565(second)
    colors = [(*c0, 255), (*c1, 255)]
    if first > second or not allow_transparent:
        colors.extend(
            (
                ((2 * c0[0] + c1[0]) // 3, (2 * c0[1] + c1[1]) // 3, (2 * c0[2] + c1[2]) // 3, 255),
                ((c0[0] + 2 * c1[0]) // 3, (c0[1] + 2 * c1[1]) // 3, (c0[2] + 2 * c1[2]) // 3, 255),
            )
        )
    else:
        colors.extend(
            (
                ((c0[0] + c1[0]) // 2, (c0[1] + c1[1]) // 2, (c0[2] + c1[2]) // 2, 255),
                (0, 0, 0, 0),
            )
        )
    return tuple(colors)


def _decode_dxt(data: bytes, width: int, height: int, fourcc: bytes) -> bytes:
    block_size = 8 if fourcc == b"DXT1" else 16
    rgba = bytearray(width * height * 4)
    offset = 0
    for block_y in range(0, height, 4):
        for block_x in range(0, width, 4):
            if offset + block_size > len(data):
                raise ValueError("DDS block data is truncated")
            block = data[offset : offset + block_size]
            offset += block_size
            alphas: tuple[int, ...]
            if fourcc == b"DXT1":
                colors = _dxt_colors(block, allow_transparent=True)
                color_bits = struct.unpack_from("<I", block, 4)[0]
                alphas = (255,) * 16
            elif fourcc == b"DXT3":
                colors = _dxt_colors(block[8:], allow_transparent=False)
                alpha_bits = int.from_bytes(block[:8], "little")
                alphas = tuple(((alpha_bits >> (index * 4)) & 0xF) * 17 for index in range(16))
                color_bits = struct.unpack_from("<I", block, 12)[0]
            elif fourcc == b"DXT5":
                colors = _dxt_colors(block[8:], allow_transparent=False)
                alpha0, alpha1 = block[0], block[1]
                alpha_values = [alpha0, alpha1]
                if alpha0 > alpha1:
                    alpha_values.extend(
                        (
                            (6 * alpha0 + alpha1) // 7,
                            (5 * alpha0 + 2 * alpha1) // 7,
                            (4 * alpha0 + 3 * alpha1) // 7,
                            (3 * alpha0 + 4 * alpha1) // 7,
                            (2 * alpha0 + 5 * alpha1) // 7,
                            (alpha0 + 6 * alpha1) // 7,
                        )
                    )
                else:
                    alpha_values.extend(
                        (
                            (4 * alpha0 + alpha1) // 5,
                            (3 * alpha0 + 2 * alpha1) // 5,
                            (2 * alpha0 + 3 * alpha1) // 5,
                            (alpha0 + 4 * alpha1) // 5,
                            0,
                            255,
                        )
                    )
                alpha_bits = int.from_bytes(block[2:8], "little")
                alphas = tuple(alpha_values[(alpha_bits >> (index * 3)) & 0x7] for index in range(16))
                color_bits = struct.unpack_from("<I", block, 12)[0]
            else:
                raise ValueError(f"unsupported DDS compression {fourcc!r}")
            for local_y in range(4):
                for local_x in range(4):
                    x = block_x + local_x
                    y = block_y + local_y
                    if x >= width or y >= height:
                        continue
                    index = local_y * 4 + local_x
                    color = colors[(color_bits >> (index * 2)) & 0x3]
                    pixel = (y * width + x) * 4
                    rgba[pixel : pixel + 4] = bytes((*color[:3], alphas[index]))
    return bytes(rgba)


def decode_dds(data: bytes) -> QImage:
    """Decode the DDS formats used by official X-Ray icon atlases."""

    if len(data) < _DDS_HEADER_SIZE or data[:4] != b"DDS ":
        raise ValueError("not a DDS image")
    height = _u32(data, 12)
    width = _u32(data, 16)
    if not width or not height or width * height > 16_777_216:
        raise ValueError("DDS dimensions are invalid")
    pixel_flags = _u32(data, 80)
    fourcc = data[84:88]
    if pixel_flags & 0x4:
        rgba = _decode_dxt(data[_DDS_HEADER_SIZE:], width, height, fourcc)
    elif pixel_flags & 0x40:
        bits = _u32(data, 88)
        if bits not in {24, 32}:
            raise ValueError("unsupported uncompressed DDS pixel size")
        bytes_per_pixel = bits // 8
        pitch = _u32(data, 20) or width * bytes_per_pixel
        red_mask = _u32(data, 92)
        green_mask = _u32(data, 96)
        blue_mask = _u32(data, 100)
        alpha_mask = _u32(data, 104)
        rgba_buffer = bytearray(width * height * 4)
        payload = data[_DDS_HEADER_SIZE:]
        for y in range(height):
            row_start = y * pitch
            for x in range(width):
                start = row_start + x * bytes_per_pixel
                if start + bytes_per_pixel > len(payload):
                    raise ValueError("DDS pixel data is truncated")
                value = int.from_bytes(payload[start : start + bytes_per_pixel], "little")
                pixel = (y * width + x) * 4
                rgba_buffer[pixel : pixel + 4] = bytes(
                    (
                        _channel(value, red_mask),
                        _channel(value, green_mask),
                        _channel(value, blue_mask),
                        _channel(value, alpha_mask) if alpha_mask else 255,
                    )
                )
        rgba = bytes(rgba_buffer)
    else:
        raise ValueError("unsupported DDS pixel format")
    return QImage(rgba, width, height, width * 4, _RGBA_FORMAT).copy()


def category_icon(category: str | None, size: int = 28) -> QIcon:
    """Draw a small repository-owned fallback glyph in the Zone palette."""

    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = _CATEGORY_COLORS.get(str(category).casefold(), QColor("#b4aa91"))
    painter.setPen(color)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    margin = max(3, size // 7)
    rect = QRect(margin, margin, size - 2 * margin, size - 2 * margin)
    normalized = str(category).casefold()
    if normalized == "weapon":
        painter.drawLine(margin, size - margin, size - margin, margin + 3)
        painter.drawLine(margin + 3, size - margin - 2, margin + 9, size - margin - 2)
        painter.drawLine(size - margin - 5, margin + 2, size - margin, margin + 2)
    elif normalized == "ammo":
        painter.drawRect(rect)
        painter.drawLine(margin + 3, margin + 5, size - margin - 3, margin + 5)
        painter.drawLine(margin + 3, size // 2, size - margin - 3, size // 2)
    elif normalized == "outfit":
        path = QPainterPath()
        path.moveTo(size // 2, margin)
        path.lineTo(size - margin, margin + 7)
        path.lineTo(size - margin - 3, size - margin)
        path.lineTo(margin + 3, size - margin)
        path.lineTo(margin, margin + 7)
        path.closeSubpath()
        painter.drawPath(path)
    elif normalized == "artifact":
        painter.drawEllipse(rect)
        painter.drawLine(size // 2, margin + 3, size // 2, size - margin - 3)
        painter.drawLine(margin + 3, size // 2, size - margin - 3, size // 2)
    elif normalized == "consumable":
        painter.drawRoundedRect(rect, size / 4, size / 4)
        painter.drawLine(margin + 4, size // 2, size - margin - 4, size // 2)
    elif normalized == "grenade":
        painter.drawEllipse(rect)
        painter.drawLine(size // 2, margin, size // 2 + 4, margin - 2)
    else:
        painter.drawRect(rect)
        painter.drawPoint(size // 2, size // 2)
    painter.end()
    return QIcon(canvas)


class XRayIconResolver:
    """Resolve item atlas crops without changing the selected game install."""

    def __init__(self, catalog: ItemCatalog | None) -> None:
        self.catalog = catalog
        self._atlas_cache: dict[Path, QImage | None] = {}
        self._packed_atlas_cache: dict[tuple[Path, str], QImage | None] = {}
        self._icon_cache: dict[tuple[object, ...], QIcon] = {}

    def icon_for(self, definition: ItemDefinition, *, size: int = 30) -> QIcon:
        cache_key = (
            definition.key,
            definition.icon_texture,
            definition.icon_x,
            definition.icon_y,
            definition.width,
            definition.height,
            size,
        )
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]
        icon = self._atlas_icon(definition, size=size)
        if icon is None:
            icon = category_icon(definition.category, size=size)
        self._icon_cache[cache_key] = icon
        return icon

    def icon_for_key(self, key: str, category: str | None = None, size: int = 30) -> QIcon:
        definition = self.catalog.resolve(key) if self.catalog is not None else None
        if definition is not None:
            return self.icon_for(definition, size=size)
        return category_icon(category, size=size)

    def _atlas_icon(self, definition: ItemDefinition, *, size: int) -> QIcon | None:
        if (
            self.catalog is None
            or self.catalog.source_root is None
            or definition.icon_x is None
            or definition.icon_y is None
        ):
            return None
        source_root = self.catalog.source_root
        path = self._atlas_path(source_root, definition.icon_texture)
        if path is not None:
            atlas = self._atlas_cache.get(path)
            if path not in self._atlas_cache:
                try:
                    atlas = decode_dds(path.read_bytes())
                except (OSError, ValueError, struct.error):
                    atlas = None
                self._atlas_cache[path] = atlas
        else:
            texture_name = (definition.icon_texture or "ui_icon_equipment").replace("\\", "/")
            packed_key = (source_root, texture_name.casefold())
            atlas = self._packed_atlas_cache.get(packed_key)
            if packed_key not in self._packed_atlas_cache:
                try:
                    raw = read_xray_asset(source_root, texture_name)
                    atlas = decode_dds(raw) if raw is not None else None
                except (OSError, ValueError, struct.error):
                    atlas = None
                self._packed_atlas_cache[packed_key] = atlas
        if atlas is None:
            return None
        width = max(1, definition.width or 1) * _ICON_CELL_SIZE
        height = max(1, definition.height or 1) * _ICON_CELL_SIZE
        x = definition.icon_x * _ICON_CELL_SIZE
        y = definition.icon_y * _ICON_CELL_SIZE
        if x >= atlas.width() or y >= atlas.height():
            return None
        crop = atlas.copy(QRect(x, y, width, height))
        if crop.isNull():
            return None
        return QIcon(
            QPixmap.fromImage(
                crop.scaled(
                    size,
                    size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        )

    @staticmethod
    def _atlas_path(source_root: Path, texture: str | None) -> Path | None:
        # A packed catalog may have been selected specifically because an
        # unpacked tree contained a mod overlay. Never read that overlay for
        # visual assets: packed official volumes are handled separately above.
        if source_root.name.casefold() != "gamedata":
            return None
        texture_name = (texture or "ui_icon_equipment").replace("\\", "/").strip()
        relative = (
            texture_name
            if texture_name.lower().endswith(".dds")
            else f"{texture_name}.dds"
        )
        relative_path = Path(relative)
        roots = [source_root]
        candidates: list[Path] = []
        for root in roots:
            candidates.extend(
                (
                    root / "textures" / relative_path,
                    root / relative_path,
                    root / "textures" / "ui" / relative_path.name,
                )
            )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None


__all__ = ["XRayIconResolver", "category_icon", "decode_dds"]
