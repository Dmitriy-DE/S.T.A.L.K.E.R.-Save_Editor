from __future__ import annotations

from pathlib import Path

import pytest
from test_xray_save import _ammo_catalog, _fixture, _fixture_with_base_item

from editor.models import EditPlan, SourceRef
from editor.xray_save import COP_FORMAT, XRaySaveError, parse_xray, prepare_xray


def _source(data: bytes) -> SourceRef:
    import hashlib

    return SourceRef(
        kind="local",
        locator="items-fixture.scop",
        sha256=hashlib.sha256(data).hexdigest(),
    )


def test_catalog_item_add_and_delete_are_round_trip_verified() -> None:
    data = _fixture()
    before = parse_xray(data, COP_FORMAT)
    added = prepare_xray(
        data,
        EditPlan(source=_source(data), adds=(("ammo_new", 2, "inventory"),)),
        COP_FORMAT,
        catalog=_ammo_catalog(),
    )
    after_add = parse_xray(added.data, COP_FORMAT)
    assert len(after_add.inventory) == len(before.inventory) + 1
    assert added.data != data

    removed = prepare_xray(
        added.data,
        EditPlan(source=_source(added.data), detach=((0x1234, True),)),
        COP_FORMAT,
    )
    with pytest.raises(XRaySaveError, match="не найден"):
        parse_xray(removed.data, COP_FORMAT).object_by_id(0x1234)


def test_non_stack_item_remains_read_only_for_count_edits() -> None:
    data = _fixture_with_base_item()
    item = parse_xray(data, COP_FORMAT).inventory[0]

    assert item.count is None
    assert item.editable_count is False
    with pytest.raises(XRaySaveError, match="count|stack"):
        prepare_xray(
            data,
            EditPlan(source=_source(data), stacks=((item.handle, 2),)),
            COP_FORMAT,
        )


def test_item_change_surfaces_keep_unproven_mutations_read_only() -> None:
    detail = Path(__file__).parents[1] / "ui" / "item_detail_view.py"
    browser = Path(__file__).parents[1] / "web" / "app.js"

    assert "S2 add/remove surface is omitted" in detail.read_text(encoding="utf-8")
    assert "backup обязателен" in browser.read_text(encoding="utf-8")
    assert "ОПАСНО" in browser.read_text(encoding="utf-8")
