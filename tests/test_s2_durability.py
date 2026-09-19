from __future__ import annotations

import hashlib

import pytest
from test_s2_equipment_inventory import EQUIPPED_HANDLE, _save_with_equipped_armor

import save_format as sf
from editor.models import EditPlan, SourceRef
from editor.prepare import prepare_edit


def _source(data: bytes) -> SourceRef:
    return SourceRef(
        kind="local",
        locator="s2-equipment-fixture.sav",
        sha256=hashlib.sha256(data).hexdigest(),
    )


def test_s2_prepare_edit_round_trips_armor_condition_and_only_changes_f32(
    synthetic_save: bytes,
) -> None:
    data = _save_with_equipped_armor(synthetic_save)
    before_raw = sf.decompress_save(data)
    before = sf.inspect_save(data)
    item = next(item for item in before.inventory if item.handle == EQUIPPED_HANDLE)
    assert item.condition == pytest.approx(0.75)

    prepared = prepare_edit(
        data,
        EditPlan(source=_source(data), durability=((EQUIPPED_HANDLE, 0.9),)),
    )

    after_raw = sf.decompress_save(prepared.data)
    after = sf.inspect_save(prepared.data)
    edited = next(item for item in after.inventory if item.handle == EQUIPPED_HANDLE)
    changed = {
        index
        for index, (left, right) in enumerate(zip(before_raw, after_raw, strict=True))
        if left != right
    }
    expected = set(range(item.record_offset + 0x23 + 4, item.record_offset + 0x23 + 8))
    assert changed <= expected
    assert changed
    assert edited.condition == pytest.approx(0.9)
    assert after.crc_ok is True


def test_s2_prepare_edit_can_combine_money_and_armor_condition(
    synthetic_save: bytes,
) -> None:
    data = _save_with_equipped_armor(synthetic_save)

    prepared = prepare_edit(
        data,
        EditPlan(
            source=_source(data),
            money=900_000,
            durability=((EQUIPPED_HANDLE, 1.0),),
        ),
    )

    after = sf.inspect_save(prepared.data)
    edited = next(item for item in after.inventory if item.handle == EQUIPPED_HANDLE)
    assert after.money == 900_000
    assert edited.condition == pytest.approx(1.0)


def test_s2_prepare_edit_rejects_non_armor_condition(synthetic_save: bytes) -> None:
    data = _save_with_equipped_armor(
        synthetic_save,
        display_name="GunBucket_MagIncreased",
    )
    item = next(
        item for item in sf.inspect_save(data).inventory if item.handle == EQUIPPED_HANDLE
    )
    assert item.condition is not None
    assert item.condition_editable is False
    with pytest.raises(sf.SaveError, match="S2 armor condition|condition"):
        prepare_edit(
            data,
            EditPlan(
                source=_source(data),
                durability=((EQUIPPED_HANDLE, 0.5),),
            ),
        )


def test_s2_prepare_edit_rejects_stale_source(synthetic_save: bytes) -> None:
    data = _save_with_equipped_armor(synthetic_save)
    stale = bytearray(data)
    stale[-1] ^= 1
    with pytest.raises(sf.SaveError, match="Источник изменился"):
        prepare_edit(
            bytes(stale),
            EditPlan(source=_source(data), durability=((EQUIPPED_HANDLE, 0.5),)),
        )


def test_s2_prepare_edit_rejects_unproven_upgrade_writer(synthetic_save: bytes) -> None:
    with pytest.raises(sf.SaveError, match="улучш|upgrade"):
        prepare_edit(
            synthetic_save,
            EditPlan(
                source=_source(synthetic_save),
                upgrades=((1, ("Armor_Upgrade_Test",)),),
            ),
        )
