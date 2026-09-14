from __future__ import annotations

import hashlib

import pytest

import save_format as sf
from editor.formats import by_id, detect, formats
from editor.models import EditPlan, SourceRef
from editor.prepare import prepare_edit


def _plan(data: bytes) -> EditPlan:
    return EditPlan(
        source=SourceRef(
            kind="local",
            locator="/tmp/synthetic-save.sav",
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        money=900_000,
    )


def test_registry_starts_with_only_stalker2(synthetic_save: bytes) -> None:
    registered = formats()

    assert [item.id for item in registered] == ["stalker2"]
    assert by_id("stalker2") is registered[0]
    assert detect(synthetic_save) is registered[0]


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
