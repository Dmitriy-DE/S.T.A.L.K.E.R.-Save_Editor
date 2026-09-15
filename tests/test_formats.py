from __future__ import annotations

import hashlib

import pytest
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
    ]
    assert by_id("stalker2") is registered[0]
    assert detect(synthetic_save) is registered[0]


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
