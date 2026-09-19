from __future__ import annotations

from dataclasses import replace

import pytest

from editor.equipment import equipment_items
from editor.equipment_edits import (
    stage_bulk_repair,
    stage_repair,
)
from save_format import InventoryItem


def _item(
    handle: int,
    key: str,
    category: str,
    *,
    storage: str | None,
    condition: float | None,
    editable: bool,
) -> InventoryItem:
    return InventoryItem(
        handle=handle,
        x=None,
        y=None,
        width=None,
        height=None,
        cells=(),
        count=1,
        total_weight=None,
        unit_weight=None,
        kind_code=1,
        category=category,
        record_offset=0,
        record_end_guess=64,
        fingerprint="f" * 64,
        type_key=key,
        editable_count=False,
        display_name=key,
        condition=condition,
        condition_editable=editable,
        storage=storage,  # type: ignore[arg-type]
    )


def _rows():
    rows = equipment_items(
        (
            _item(1, "wpn_a", "Оружие", storage="equipped", condition=0.5, editable=True),
            _item(2, "outfit_a", "Броня/экипировка", storage="inventory", condition=0.75, editable=True),
            _item(3, "helm_a", "Броня/экипировка", storage="equipped", condition=1.0, editable=True),
            _item(4, "opaque_a", "Разное", storage=None, condition=None, editable=False),
        ),
        release_id="stalker-cop",
    )
    return tuple(replace(row, handle=index) for index, row in enumerate(rows, 1))


def test_stage_repair_accepts_0_50_and_100_percent() -> None:
    rows = _rows()

    assert stage_repair(rows, (1,), 0).changes == ((1, 0.0),)
    assert stage_repair(rows, (2,), 50).changes == ((2, 0.5),)
    assert stage_repair(rows, (1,), 100).changes == ((1, 1.0),)


def test_stage_repair_rejects_invalid_percentage() -> None:
    rows = _rows()

    with pytest.raises(ValueError, match="0.*100"):
        stage_repair(rows, (1,), -1)
    with pytest.raises(ValueError, match="0.*100"):
        stage_repair(rows, (1,), 101)
    with pytest.raises(ValueError, match="finite"):
        stage_repair(rows, (1,), float("nan"))


def test_bulk_repair_filters_damaged_equipped_and_categories() -> None:
    rows = _rows()

    damaged = stage_bulk_repair(rows, "damaged", 100)
    assert damaged.changes == ((1, 1.0), (2, 1.0))

    equipped = stage_bulk_repair(rows, "equipped", 100)
    assert equipped.changes == ((1, 1.0),)
    assert any(skip.handle == 3 and "no-op" in skip.reason for skip in equipped.skipped)

    weapons = stage_bulk_repair(rows, "weapon", 0)
    assert weapons.changes == ((1, 0.0),)


def test_bulk_repair_reports_unsafe_and_unknown_items_instead_of_staging() -> None:
    rows = _rows()
    result = stage_repair(rows, (4, 99), 100)

    assert result.changes == ()
    assert [skip.handle for skip in result.skipped] == [4, 99]
    assert "condition" in result.skipped[0].reason
    assert "not found" in result.skipped[1].reason


def test_s2_research_rows_are_never_writable_from_bulk_repair() -> None:
    item = _item(7, "weapon_candidate", "Оружие", storage="inventory", condition=0.5, editable=True)
    row = equipment_items((item,), release_id="stalker2")[0]

    result = stage_repair((row,), (7,), 100)

    assert result.changes == ()
    assert result.skipped[0].handle == 7
    assert "research" in result.skipped[0].reason
