from __future__ import annotations

from editor.capabilities import FormatCapabilities, gate_mutations_for_release
from editor.formats import by_id


def test_capabilities_are_immutable_and_default_to_read_only() -> None:
    capabilities = FormatCapabilities(read_inventory=True)

    assert capabilities.read_inventory is True
    assert capabilities.edit_money is False
    assert capabilities.add_items is False

    try:
        capabilities.edit_money = True  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("capabilities must be immutable")


def test_unverified_release_keeps_only_explicit_experimental_mutations() -> None:
    capabilities = gate_mutations_for_release(
        "stalker2",
        FormatCapabilities(
            read_inventory=True,
            edit_money=True,
            edit_stacks=True,
            experimental_fields=frozenset({"edit_money"}),
        ),
    )

    assert capabilities.edit_money is True
    assert capabilities.is_experimental("edit_money") is True
    assert capabilities.edit_stacks is False
    assert capabilities.experimental_fields == frozenset({"edit_money"})


def test_registered_formats_expose_release_and_capability_metadata() -> None:
    s2 = by_id("stalker2")
    cop = by_id("stalker-cop")

    assert s2.release_id == "stalker2"
    assert s2.edition == "s2"
    assert s2.capabilities.read_inventory is True
    assert s2.capabilities.edit_money is True
    assert s2.capabilities.is_experimental("edit_money") is True
    assert s2.capabilities.edit_stacks is False

    assert cop.release_id == "stalker-cop"
    assert cop.edition == "original"
    assert cop.capabilities.read_inventory is True
    assert cop.capabilities.edit_stacks is True
    assert cop.capabilities.add_items is True
    assert cop.capabilities.remove_items is True
    assert cop.capabilities.edit_upgrades is True
    assert cop.capabilities.is_experimental("edit_upgrades") is True
    assert cop.capabilities.edit_placement is True
    assert cop.capabilities.is_experimental("edit_placement") is True

    soc = by_id("stalker-soc")
    assert soc.capabilities.edit_upgrades is False
    assert soc.capabilities.edit_placement is True
    assert cop.capabilities.catalog is True
