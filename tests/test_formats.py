from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from test_xray_catalog import _write_unpacked_fixture
from test_xray_save import _fixture

import save_format as sf
from editor.formats import by_id, detect, detect_fast, formats
from editor.models import EditPlan, SourceRef
from editor.prepare import prepare_edit
from editor.xray_save import COP_FORMAT, CS_FORMAT, SOC_FORMAT


def _plan(data: bytes) -> EditPlan:
    return EditPlan(
        source=SourceRef(
            kind="local",
            locator="/tmp/synthetic-save.sav",
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        money=900_000,
    )


def test_registry_contains_stalker2_and_original_xray_families(synthetic_save: bytes) -> None:
    registered = formats()

    assert [item.id for item in registered] == [
        "stalker2",
        "stalker-soc",
        "stalker-cs",
        "stalker-cop",
        "stalker-soc-ee",
        "stalker-cs-ee",
        "stalker-cop-ee",
    ]
    assert by_id("stalker2") is registered[0]
    assert detect(synthetic_save) is registered[0]
    assert registered[0].release_id == "stalker2"
    assert registered[0].edition == "s2"
    assert registered[1].release_id == "stalker-soc"
    assert registered[2].release_id == "stalker-cs"
    assert registered[3].release_id == "stalker-cop"


@pytest.mark.parametrize(
    ("spec", "fixture_version", "outer_version"),
    (
        (SOC_FORMAT, 118, 3),
        (CS_FORMAT, 124, 5),
        (COP_FORMAT, 128, 6),
    ),
)
def test_registry_detects_each_original_xray_family(spec, fixture_version: int, outer_version: int) -> None:
    data = _fixture(fixture_version, outer_version)

    assert detect(data) is by_id(spec.id)
    assert detect_fast(data) is by_id(spec.id)


def test_registry_returns_none_for_unknown_bytes() -> None:
    assert detect(b"not a save") is None


def test_by_id_rejects_unknown_format() -> None:
    with pytest.raises(KeyError):
        by_id("unknown")


def test_stalker2_adapter_delegates_existing_parser_and_prepare(
    synthetic_save: bytes,
) -> None:
    format_ = by_id("stalker2")
    plan = _plan(synthetic_save)

    assert format_.inspect(synthetic_save) == sf.inspect_save(synthetic_save)
    assert format_.prepare(synthetic_save, plan) == prepare_edit(synthetic_save, plan)


def test_service_inspection_preserves_parser_result_and_format_metadata(
    synthetic_save: bytes,
) -> None:
    from editor.service import EditorService

    result = EditorService().inspect_result(synthetic_save)

    assert result.format_id == "stalker2"
    assert result.format_title == "S.T.A.L.K.E.R. 2: Heart of Chornobyl"
    assert result.info == sf.inspect_save(synthetic_save)


def test_service_passes_explicit_s2_catalog_root_to_cloud_style_source(
    synthetic_save: bytes, tmp_path: Path
) -> None:
    from editor.service import EditorService

    item_root = tmp_path / "Content" / "GameLite" / "GameData" / "ItemPrototypes"
    item_root.mkdir(parents=True)
    (item_root / "Items.cfg").write_text(
        """
Bandage : struct.begin
    SID = Bandage
    Type = EItemPrototypeType::Consumable
    DisplayName = UI_Item_Bandage
struct.end
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = EditorService().inspect_result(
        synthetic_save,
        source_name="Stalker2/Saved/STEAM/SaveGames/Data/slot.sav",
        catalog_roots=(tmp_path,),
    )

    assert result.catalog is not None
    assert result.catalog.source_root == tmp_path
    assert result.catalog.resolve("Bandage") is not None


def test_service_inspection_projects_common_release_capabilities(
    synthetic_save: bytes,
) -> None:
    from editor.service import EditorService

    result = EditorService().inspect_result(synthetic_save)

    assert result.release_id == "stalker2"
    assert result.edition == "s2"
    assert result.capabilities.edit_money is True
    assert result.capabilities.is_experimental("edit_money") is True
    assert result.capabilities.edit_stacks is True
    assert result.capabilities.is_experimental("edit_stacks") is True
    assert result.capabilities.add_items is False


def test_original_xray_format_finds_catalog_from_a_save_path(tmp_path) -> None:
    game_root = tmp_path / "cop"
    _write_unpacked_fixture(game_root)
    save_dir = game_root / "_appdata_" / "savedgames"
    save_dir.mkdir(parents=True)
    save_path = save_dir / "slot.scop"
    save_path.write_bytes(_fixture(128, 6))

    format_ = by_id("stalker-cop")
    catalog = format_.catalog_for_source(str(save_path))

    assert catalog is not None
    assert catalog.resolve("ammo_test") is not None


def test_s2_launch_layout_is_diagnosed_but_never_accepted() -> None:
    import save_format as sf
    from editor.formats import STALKER2_FORMAT
    from ui.ux_copy import classify_analysis_error

    raw = b"HEADER" + b"\x65\x72\xe2\x28\x00\x00\x01\x10" + sf.WALLET_FIELD_ID + b"\x0d\x00" * 8
    data = sf.rebuild_uncompressed(raw)

    assert not STALKER2_FORMAT.detect(data)
    reason = STALKER2_FORMAT.detection_reason(data)
    assert reason.startswith("legacy S2 layout")
    assert classify_analysis_error(reason) == "old_s2_save"
    assert classify_analysis_error("подтверждённая wallet anchor встречается 0 раз(а)") == "open"


def test_s2_prepare_refuses_fields_the_capability_matrix_keeps_read_only(synthetic_save: bytes) -> None:
    import hashlib

    import pytest

    from editor.formats import STALKER2_FORMAT
    from editor.models import EditPlan, SourceRef
    from save_format import SaveError

    source = SourceRef(kind="local", locator="slot.sav", sha256=hashlib.sha256(synthetic_save).hexdigest())
    # The UI hid these, but the CLI reached the S2 writer directly.
    with pytest.raises(SaveError, match="remove_items"):
        STALKER2_FORMAT.prepare(synthetic_save, EditPlan(source=source, detach=((0x30000001, False),)))
    prepared = STALKER2_FORMAT.prepare(synthetic_save, EditPlan(source=source, money=123))
    assert prepared.output_sha256


def test_stalker2_stack_edits_are_open_as_experimental_after_game_check(synthetic_save: bytes) -> None:
    """ED-3 confirmed S2 count edits in the game; they stay marked experimental."""

    from dataclasses import replace

    from editor.formats import require_plan_capabilities

    format_ = by_id("stalker2")
    support = format_.capabilities.support("edit_stacks")
    assert support.writable is True
    assert format_.capabilities.is_experimental("edit_stacks") is True
    require_plan_capabilities(format_.capabilities, replace(_plan(synthetic_save), money=None, stacks=((1, 2),)))


def test_stash_puts_use_the_add_items_capability_gate(synthetic_save: bytes) -> None:
    from dataclasses import replace

    from editor.formats import require_plan_capabilities
    from save_format import SaveError

    format_ = by_id("stalker2")
    plan = replace(
        _plan(synthetic_save),
        money=None,
        stash_puts=((0x1234, 0x10),),
    )

    with pytest.raises(SaveError, match="add_items"):
        require_plan_capabilities(format_.capabilities, plan)
