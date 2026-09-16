from __future__ import annotations

import hashlib
import struct

import pytest
from test_xray_save import _chunk, _object_record, _spawn, _state_base, _z

from editor.models import EditPlan, SourceRef
from editor.xray_container import lzo1x_compress
from editor.xray_save import (
    COP_FORMAT,
    CS_FORMAT,
    SOC_FORMAT,
    XRaySaveError,
    parse_xray,
    prepare_xray,
)


def _condition_state(version: int, condition: float) -> bytes:
    state = bytearray()
    state += struct.pack("<HfIII", 15, 2.0, 0, 56, 0)
    state += _z("[weapon]")
    state += struct.pack("<II", 0, 0)
    state += _z("weapon.ogf")
    state += b"\x00"  # visual flags
    state += struct.pack("<f", condition)
    if version > 123:
        state += struct.pack("<I", 0)  # empty m_upgrades vector
    return bytes(state)


def _condition_fixture(
    *,
    version: int,
    outer: int,
    name: str = "wpn_test",
    condition: float = 0.25,
    update_condition_offset: int = 3,
    client_place: int | None = None,
) -> bytes:
    actor = _spawn(
        "actor",
        0,
        0xFFFF,
        version,
        _state_base(version, money=1234),
        struct.pack("<H", 0),
    )
    update = bytearray(8)
    struct.pack_into("<H", update, 0, 0)
    update[update_condition_offset] = round(condition * 255)
    if client_place is None:
        client_data = b""
    elif outer in {3, 5}:
        client_data = struct.pack("<HfB", client_place, condition, 0)
    else:
        client_data = b"\x02" + struct.pack("<HfB", client_place, condition, 0)
    item = _spawn(
        name,
        0x3456,
        0,
        version,
        _condition_state(version, condition),
        bytes(update),
        client_data,
    )
    objects = struct.pack("<I", 2) + _object_record(actor, struct.pack("<H", 0)) + _object_record(item, bytes(update))
    raw = b"".join(
        (
            _chunk(0, struct.pack("<I", outer)),
            _chunk(5, struct.pack("<Qff", 123456, 10.0, 1.0)),
            _chunk(1, b"\x00" * 8),
            _chunk(2, objects),
            _chunk(9, b"registry"),
        )
    )
    return struct.pack("<III", 0xFFFFFFFF, outer, len(raw)) + lzo1x_compress(raw)


def _source(data: bytes) -> SourceRef:
    return SourceRef(
        kind="local",
        locator="condition-fixture.sav",
        sha256=hashlib.sha256(data).hexdigest(),
    )


@pytest.mark.parametrize(
    ("spec", "version", "outer", "name", "update_offset"),
    (
        (SOC_FORMAT, 118, 3, "wpn_test", 3),
        (CS_FORMAT, 124, 5, "dolg_exo_outfit", 3),
        (COP_FORMAT, 128, 6, "wpn_test", 4),
    ),
)
def test_xray_reads_condition_for_original_release_targets(
    spec, version: int, outer: int, name: str, update_offset: int
) -> None:
    data = _condition_fixture(
        version=version,
        outer=outer,
        name=name,
        update_condition_offset=update_offset,
    )

    parsed = parse_xray(data, spec)
    obj = parsed.object_by_id(0x3456)
    item = parsed.inventory[0]

    assert obj.condition == pytest.approx(0.25)
    assert obj.condition_offset is not None
    assert obj.update_condition_offset == obj.update_offset + update_offset
    assert item.condition == pytest.approx(0.25)
    assert item.condition_editable is True
    assert item.storage is None
    assert "durability" not in obj.unknown_fields


@pytest.mark.parametrize(
    ("spec", "version", "outer", "update_offset"),
    (
        (SOC_FORMAT, 118, 3, 3),
        (CS_FORMAT, 124, 5, 3),
        (COP_FORMAT, 128, 6, 4),
    ),
)
def test_xray_prepare_patches_state_and_matching_update_condition(
    spec, version: int, outer: int, update_offset: int
) -> None:
    data = _condition_fixture(
        version=version,
        outer=outer,
        update_condition_offset=update_offset,
    )
    plan = EditPlan(source=_source(data), durability=((0x3456, 0.75),))

    prepared = prepare_xray(data, plan, spec)
    after = parse_xray(prepared.data, spec)
    obj = after.object_by_id(0x3456)

    assert prepared.data != data
    assert obj.condition == pytest.approx(0.75)
    assert after.inventory[0].condition == pytest.approx(0.75)
    assert after.container.raw[obj.update_offset + update_offset] == round(0.75 * 255)


def test_xray_condition_writer_updates_client_mirror_and_reports_storage() -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=0x0411,  # source layout: slot 1, base slot 1
    )

    parsed = parse_xray(data, COP_FORMAT)
    item = parsed.inventory[0]
    obj = parsed.object_by_id(item.handle)

    assert item.storage == "equipped"
    assert item.position == "экипировано (слот подтверждён)"
    assert obj.client_condition_offset is not None

    prepared = prepare_xray(
        data,
        EditPlan(source=_source(data), durability=((item.handle, 0.75),)),
        COP_FORMAT,
    )
    after = parse_xray(prepared.data, COP_FORMAT)
    checked = after.object_by_id(item.handle)

    assert checked.client_condition_offset is not None
    assert struct.unpack_from("<f", after.container.raw, checked.client_condition_offset)[0] == pytest.approx(0.75)


def test_xray_condition_reader_reports_inventory_and_rejects_invalid_slot() -> None:
    inventory = parse_xray(
        _condition_fixture(version=128, outer=6, client_place=0x0013),
        COP_FORMAT,
    ).inventory[0]
    assert inventory.storage == "inventory"
    assert inventory.position == "инвентарь actor"

    invalid = parse_xray(
        _condition_fixture(version=128, outer=6, client_place=(1 | (63 << 4) | (63 << 10))),
        COP_FORMAT,
    ).inventory[0]
    assert invalid.storage is None
    assert invalid.position == "инвентарь actor; слот не определён"


def test_xray_durability_rejects_unknown_item_and_invalid_values() -> None:
    from test_xray_save import _fixture_with_base_item

    data = _fixture_with_base_item()
    item = parse_xray(data, COP_FORMAT).inventory[0]
    assert item.condition is None
    assert item.condition_editable is False

    with pytest.raises(XRaySaveError, match="condition|прочност|durability"):
        prepare_xray(
            data,
            EditPlan(source=_source(data), durability=((item.handle, 0.5),)),
            COP_FORMAT,
        )

    with pytest.raises(ValueError, match="[Dd]urability"):
        EditPlan(source=_source(data), durability=((item.handle, 1.1),))


def test_edit_plan_freezes_and_rejects_duplicate_durability_handles() -> None:
    data = _condition_fixture(version=128, outer=6)
    staged = [(0x3456, 0.5)]
    plan = EditPlan(source=_source(data), durability=staged)
    staged[0] = (0x3456, 0.9)

    assert plan.durability == ((0x3456, 0.5),)
    with pytest.raises(ValueError, match="durability"):
        EditPlan(
            source=_source(data),
            durability=((0x3456, 0.5), (0x3456, 0.6)),
        )


def test_qt_condition_editor_stages_percentage_without_mutating_snapshot(qtbot, tmp_path) -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt

    from editor.capabilities import FormatCapabilities
    from editor.service import EditorService
    from editor.xray_save import inspect_xray
    from ui.main_window import LocalSnapshot, MainWindow

    data = _condition_fixture(version=128, outer=6)
    info = inspect_xray(data, COP_FORMAT)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window._render_snapshot(
        LocalSnapshot(
            path=tmp_path / "condition.scop",
            data=data,
            info=info,
            format_id=COP_FORMAT.id,
            format_title=COP_FORMAT.title,
            release_id=COP_FORMAT.id,
            edition="original",
            capabilities=FormatCapabilities(
                read_inventory=True,
                edit_durability=True,
                experimental_fields=frozenset({"edit_durability"}),
            ),
        )
    )

    view = window.inventory_view
    view.table.selectRow(0)
    qtbot.waitUntil(lambda: view.selected_handle == 0x3456)
    assert view.condition_spin.isEnabled()
    assert view.condition_spin.value() == 25
    assert "Экспериментально" in view.condition_status_label.text()

    view.condition_spin.setValue(75)
    qtbot.mouseClick(view.condition_stage_button, Qt.MouseButton.LeftButton)

    assert window.staged_durability == {0x3456: pytest.approx(0.75)}
    assert window.snapshot.data == data
    assert window._build_edit_plan().durability == ((0x3456, 0.75),)
