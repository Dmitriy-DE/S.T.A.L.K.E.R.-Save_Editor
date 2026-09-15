from __future__ import annotations

from pathlib import Path

import pytest

from editor.catalog import ItemCatalog, ItemDefinition


def test_item_definition_and_catalog_are_immutable_and_resolvable(tmp_path: Path) -> None:
    item = ItemDefinition(
        key="ammo_test",
        display_name="Test ammunition",
        category="ammo",
        unit_weight=0.25,
        width=1,
        height=1,
        max_stack=30,
        slots=("8",),
        prototype=None,
        source="gamedata/config/items.ltx#ammo_test",
    )
    catalog = ItemCatalog("stalker-cs", tmp_path, (item,))

    assert catalog.resolve("ammo_test") == item
    assert catalog.resolve("missing") is None
    assert catalog.source_root == tmp_path
    with pytest.raises(AttributeError):
        item.key = "other"  # type: ignore[misc]


def test_catalog_rejects_duplicate_keys() -> None:
    item = ItemDefinition(
        key="same",
        display_name=None,
        category=None,
        unit_weight=None,
        width=None,
        height=None,
        max_stack=None,
        slots=(),
        prototype=None,
        source="fixture",
    )

    with pytest.raises(ValueError, match="duplicate"):
        ItemCatalog("stalker-cop", None, (item, item))

