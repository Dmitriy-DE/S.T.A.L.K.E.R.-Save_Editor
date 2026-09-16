from __future__ import annotations

import pytest

from editor.capabilities import FormatCapabilities
from editor.formats import by_id


def test_capabilities_are_immutable_and_default_to_read_only() -> None:
    capabilities = FormatCapabilities(read_inventory=True)

    assert capabilities.read_inventory is True
    assert capabilities.edit_money is False
    assert capabilities.add_items is False
    assert capabilities.edit_relations is False
    assert capabilities.edit_player_faction is False

    try:
        capabilities.edit_money = True  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("capabilities must be immutable")


def test_experimental_capabilities_are_explicit_and_json_safe() -> None:
    capabilities = FormatCapabilities(
        edit_durability=True,
        edit_relations=True,
        experimental_fields=frozenset({"edit_relations", "edit_durability"}),
    )

    assert capabilities.is_experimental("edit_durability") is True
    assert capabilities.is_experimental("edit_money") is False
    assert capabilities.as_dict()["experimental_fields"] == [
        "edit_durability",
        "edit_relations",
    ]

    with pytest.raises(ValueError, match="unknown capability"):
        FormatCapabilities(experimental_fields=frozenset({"not_a_capability"}))
    with pytest.raises(ValueError, match="must be enabled"):
        FormatCapabilities(experimental_fields=frozenset({"edit_durability"}))


def test_registered_formats_expose_release_and_capability_metadata() -> None:
    s2 = by_id("stalker2")
    soc = by_id("stalker-soc")
    cop = by_id("stalker-cop")

    assert s2.release_id == "stalker2"
    assert s2.edition == "s2"
    assert s2.capabilities.read_inventory is True
    assert s2.capabilities.edit_money is False

    assert cop.release_id == "stalker-cop"
    assert cop.edition == "original"
    assert cop.capabilities.read_inventory is True
    assert cop.capabilities.edit_stacks is True
    assert cop.capabilities.add_items is True
    assert cop.capabilities.remove_items is True
    assert cop.capabilities.catalog is True
    assert cop.capabilities.edit_upgrades is True
    assert cop.capabilities.edit_durability is True
    assert cop.capabilities.edit_relations is True
    assert cop.capabilities.edit_player_faction is True
    assert set(cop.capabilities.experimental_fields) == {
        "add_items",
        "remove_items",
        "edit_durability",
        "edit_upgrades",
        "edit_relations",
        "edit_player_faction",
    }
    assert soc.capabilities.edit_upgrades is False
