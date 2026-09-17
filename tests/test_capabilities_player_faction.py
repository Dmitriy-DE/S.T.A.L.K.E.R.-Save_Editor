from __future__ import annotations

from editor.capabilities import FormatCapabilities
from editor.formats import by_id


def test_player_faction_is_explicitly_experimental_for_original_xray() -> None:
    default = FormatCapabilities(read_inventory=True)
    assert default.edit_player_faction is False
    assert "edit_player_faction" not in default.as_dict()["experimental_fields"]

    cop = by_id("stalker-cop")
    assert cop.capabilities.edit_player_faction is True
    assert cop.capabilities.is_experimental("edit_player_faction") is True
