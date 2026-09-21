from __future__ import annotations

import json

import pytest

from editor.capabilities import (
    CapabilitySupport,
    FormatCapabilities,
    gate_mutations_for_release,
)
from editor.formats import by_id, formats


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
            mutation_support={
                "edit_money": CapabilitySupport("experimental"),
                "edit_stacks": CapabilitySupport("research"),
            },
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
    assert s2.capabilities.edit_durability is True
    assert s2.capabilities.is_experimental("edit_durability") is True
    assert s2.capabilities.add_items is False
    assert s2.capabilities.edit_upgrades is False
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


def test_mutation_booleans_are_projections_of_four_state_support() -> None:
    capabilities = FormatCapabilities(
        read_inventory=True,
        mutation_support={
            "edit_money": CapabilitySupport("verified", "accepted in game"),
            "edit_stacks": CapabilitySupport("research", "needs evidence"),
            "add_items": CapabilitySupport("experimental", "round-trip only"),
            "remove_items": CapabilitySupport("unsupported"),
        },
    )

    assert capabilities.support("edit_money").maturity == "verified"
    assert capabilities.edit_money is True
    assert capabilities.edit_stacks is False
    assert capabilities.add_items is True
    assert capabilities.remove_items is False
    assert capabilities.experimental_fields == frozenset({"add_items"})
    payload = capabilities.as_dict()
    assert payload["mutation_support"]["edit_money"] == {
        "maturity": "verified",
        "reason": "accepted in game",
    }
    assert payload["mutation_support"]["edit_stacks"]["maturity"] == "research"
    assert payload["mutation_support"]["remove_items"]["maturity"] == "unsupported"
    assert payload["edit_money"] is True
    assert payload["edit_stacks"] is False


def test_mutation_support_is_immutable_and_rejects_unknown_fields() -> None:
    capabilities = FormatCapabilities(
        mutation_support={"edit_money": CapabilitySupport("research")}
    )

    with pytest.raises(TypeError):
        capabilities.mutation_support["edit_money"] = CapabilitySupport("verified")  # type: ignore[index]
    with pytest.raises(ValueError, match="unknown capability"):
        FormatCapabilities(
            mutation_support={"not_a_real_edit": CapabilitySupport("research")}
        )


def test_registered_capability_payloads_are_complete_json_projections() -> None:
    fields = {
        "edit_money",
        "edit_stacks",
        "move_items",
        "add_items",
        "remove_items",
        "edit_durability",
        "edit_upgrades",
        "edit_relations",
        "edit_player_faction",
        "edit_placement",
    }

    for format_ in formats():
        payload = format_.capabilities.as_dict()
        assert set(payload["mutation_support"]) == fields
        json.dumps(payload, ensure_ascii=False)
