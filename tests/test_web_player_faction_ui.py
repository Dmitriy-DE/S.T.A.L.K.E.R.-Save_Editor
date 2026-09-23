from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_web_player_faction_controls_use_shared_snapshot_and_bridge() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert 'id="reference-character-details"' in html
    assert 'id="reference-character"' in html
    assert "player_faction_editable" in script
    assert "state.playerFaction" in script
    assert "playerFaction" in script
    assert "JSON.stringify(state.playerFaction)" in script
