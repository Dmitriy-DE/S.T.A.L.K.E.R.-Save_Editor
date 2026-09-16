from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_web_delete_control_uses_per_item_safety_metadata() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "item.remove_editable" in script
    assert "remove.disabled" in script
    assert "item.remove_reason" in script
