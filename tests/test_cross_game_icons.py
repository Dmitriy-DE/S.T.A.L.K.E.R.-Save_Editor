"""Cross-game icon donor: borrow real art from another installed release."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor

from editor.catalog import ItemCatalog, ItemDefinition, catalog_from_items
from ui.xray_assets import XRayIconResolver, category_icon


def _rgba_dds(width: int, height: int, color_at: tuple[int, int, QColor]) -> bytes:
    header = bytearray(128)
    header[:4] = b"DDS "
    struct.pack_into("<I", header, 4, 124)
    struct.pack_into("<I", header, 8, 0x0002100F)
    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)
    struct.pack_into("<I", header, 20, width * 4)
    struct.pack_into("<I", header, 76, 32)
    struct.pack_into("<I", header, 80, 0x41)
    struct.pack_into("<I", header, 88, 32)
    struct.pack_into("<I", header, 92, 0x00FF0000)
    struct.pack_into("<I", header, 96, 0x0000FF00)
    struct.pack_into("<I", header, 100, 0x000000FF)
    struct.pack_into("<I", header, 104, 0xFF000000)
    pixels = bytearray(width * height * 4)
    x, y, color = color_at
    pixels[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes(
        (color.blue(), color.green(), color.red(), color.alpha())
    )
    return bytes(header) + bytes(pixels)


def _donor_catalog(tmp_path: Path) -> ItemCatalog:
    root = tmp_path / "gamedata"
    atlas = root / "textures" / "ui" / "ui_icon_equipment.dds"
    atlas.parent.mkdir(parents=True)
    atlas.write_bytes(_rgba_dds(100, 50, (75, 25, QColor("#3aa0ff"))))
    shared = ItemDefinition(
        key="wpn_shared",
        display_name="Shared weapon",
        category="weapon",
        unit_weight=None,
        width=1,
        height=1,
        max_stack=None,
        slots=(),
        prototype=None,
        source="gamedata/config/items.ltx#wpn_shared",
        icon_x=1,
        icon_y=0,
        icon_texture="ui_icon_equipment",
    )
    return catalog_from_items("stalker-cs", (shared,), source_root=root)


def _metadata_only_catalog() -> ItemCatalog:
    """A catalog whose game files are not installed: no source_root, no coords."""

    shared = ItemDefinition(
        key="wpn_shared",
        display_name="Shared weapon",
        category="weapon",
        unit_weight=None,
        width=1,
        height=1,
        max_stack=None,
        slots=(),
        prototype=None,
        source="generated#wpn_shared",
    )
    return catalog_from_items("stalker-cop", (shared,), source_root=None)


def test_donor_supplies_real_icon_for_shared_key(tmp_path: Path, qtbot) -> None:
    donor = XRayIconResolver(_donor_catalog(tmp_path))
    primary = _metadata_only_catalog()

    glyph = category_icon("weapon", size=24).pixmap(24, 24).toImage()

    without_donor = (
        XRayIconResolver(primary).icon_for_key("wpn_shared", "weapon", size=24)
    )
    assert without_donor.pixmap(24, 24).toImage() == glyph

    with_donor = XRayIconResolver(primary, donor=donor).icon_for_key(
        "wpn_shared", "weapon", size=24
    )
    assert with_donor.pixmap(24, 24).toImage() != glyph


def test_donor_absent_key_falls_back_to_glyph(tmp_path: Path, qtbot) -> None:
    donor = XRayIconResolver(_donor_catalog(tmp_path))
    resolver = XRayIconResolver(_metadata_only_catalog(), donor=donor)

    glyph = category_icon("ammo", size=24).pixmap(24, 24).toImage()
    result = resolver.icon_for_key("does_not_exist", "ammo", size=24)
    assert result.pixmap(24, 24).toImage() == glyph


def test_atlas_icon_for_key_never_returns_glyph() -> None:
    resolver = XRayIconResolver(_metadata_only_catalog())
    # No source_root and no coords -> no real atlas crop, and never a glyph.
    assert resolver.atlas_icon_for_key("wpn_shared", size=24) is None
    assert resolver.atlas_icon_for_key("unknown", size=24) is None


def test_bundled_pack_resolves_icons_without_any_install(qtbot) -> None:
    """The shipped pack must render real icons with no catalog and no game."""

    from ui.xray_assets import _BUNDLED_ICON_DIR

    if not (_BUNDLED_ICON_DIR / "wpn_vintorez.png").is_file():
        pytest.skip("icon pack not built in this checkout")

    resolver = XRayIconResolver(None)  # no catalog, no install
    glyph = category_icon("item", size=30).pixmap(30, 30).toImage()
    for key in ("wpn_vintorez", "medkit", "bandage", "af_medusa"):
        icon = resolver.icon_for_key(key, "item", size=30)
        assert icon.pixmap(30, 30).toImage() != glyph


def test_bundled_pack_beats_glyph_for_unpacked_key(qtbot) -> None:
    from ui.xray_assets import _BUNDLED_ICON_DIR

    resolver = XRayIconResolver(None)
    # A key that is not in the pack stays a glyph, never a crash.
    missing = resolver.icon_for_key("totally_unknown_key", "ammo", size=30)
    glyph = category_icon("ammo", size=30).pixmap(30, 30).toImage()
    assert missing.pixmap(30, 30).toImage() == glyph
    assert _BUNDLED_ICON_DIR.name == "xray"


def test_donor_only_discovered_when_own_game_missing(tmp_path: Path, monkeypatch) -> None:
    import ui.xray_assets as view

    calls: list[str | None] = []

    def fake_discover(*, prefer_not=None, **_kwargs):
        calls.append(prefer_not)
        return _donor_catalog(tmp_path)

    monkeypatch.setattr(view, "discover_icon_donor_catalog", fake_discover)
    view._DONOR_CACHE.clear()

    installed = catalog_from_items(
        "stalker-cs", (), source_root=tmp_path / "gamedata"
    )
    assert view.donor_resolver_for(installed) is None
    assert calls == []  # installed game reads its own atlas; no discovery

    missing = _metadata_only_catalog()
    resolver = view.donor_resolver_for(missing)
    assert resolver is not None
    assert calls == ["stalker-cop"]

    # Cached: a second lookup for the same release does not rescan.
    assert view.donor_resolver_for(missing) is resolver
    assert calls == ["stalker-cop"]
