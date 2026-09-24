from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_browser_reference_shell_has_four_destinations_and_state_surfaces() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    for selector in (
        'data-reference-screen="library"',
        'data-reference-screen="cloud"',
        'data-reference-screen="history"',
        'data-reference-screen="settings"',
        'id="reference-screen-library"',
        'id="reference-screen-editor"',
        'id="reference-screen-review"',
        'id="reference-inventory-table"',
        'id="reference-review-table"',
        'id="reference-save"',
    ):
        assert selector in html


def test_browser_keeps_local_only_and_does_not_use_screenshot_chrome() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    css = (ROOT / "web/style.css").read_text(encoding="utf-8")
    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert "Steam Cloud и файлы компьютера недоступны" in html
    assert "border-image" not in css
    assert "showReferenceScreen" in js
    assert "renderReferenceReview" in js


def test_browser_bundles_the_desktop_display_font_for_typographic_parity() -> None:
    css = (ROOT / "web/style.css").read_text(encoding="utf-8")
    source_font = ROOT / "assets/fonts/Oswald[wght].ttf"
    browser_font = ROOT / "web/assets/fonts/Oswald[wght].ttf"

    assert 'font-family: "Oswald"' in css
    assert browser_font.is_file()
    assert browser_font.read_bytes() == source_font.read_bytes()
