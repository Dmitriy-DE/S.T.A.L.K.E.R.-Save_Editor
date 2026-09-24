from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_web_inventory_has_accessible_zone_icon_column() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "style.css").read_text(encoding="utf-8")

    assert 'id="reference-inventory-table"' in html
    assert "itemGlyph" in script
    assert "zone-item-glyph" in script
    assert "aria-label" in script
    assert ".zone-item-glyph" in styles


def test_web_inventory_exposes_xray_placement_editor() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "renderReferenceItemDetail" in script
    assert "state.placements" in script
    assert "placement_type" in script
    assert "placement_slot" in script
    assert "placements" in script.split("state.bridge.prepare", 1)[1]
