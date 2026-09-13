from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib

import pytest

import save_format as sf
from editor.models import EditPlan, PreparedEdit, SourceRef
from editor.prepare import prepare_edit


STACK_HANDLE = 0x30000001
ORPHAN_HANDLE = 0x30000003


def _source(data: bytes, *, sha256: str | None = None) -> SourceRef:
    return SourceRef(
        kind="local",
        locator="/tmp/synthetic-save.sav",
        sha256=sha256 or hashlib.sha256(data).hexdigest(),
    )


def test_edit_plan_freezes_nested_staged_values(synthetic_save: bytes) -> None:
    staged_counts = {STACK_HANDLE: 3}
    staged_moves = {STACK_HANDLE: (2, 0)}
    staged_detach = {ORPHAN_HANDLE: True}
    staged_raw = [sf.RawPatch(0, "u8", "0", "same byte")]

    plan = EditPlan(
        source=_source(synthetic_save),
        money=900_000,
        stacks=tuple(staged_counts.items()),
        moves=tuple((handle, x, y) for handle, (x, y) in staged_moves.items()),
        detach=tuple(staged_detach.items()),
        raw=tuple(staged_raw),
    )

    staged_counts[STACK_HANDLE] = 99
    staged_moves[STACK_HANDLE] = (7, 7)
    staged_detach[ORPHAN_HANDLE] = False
    staged_raw[0] = sf.RawPatch(0, "u8", "255")

    assert plan.stacks == ((STACK_HANDLE, 3),)
    assert plan.moves == ((STACK_HANDLE, 2, 0),)
    assert plan.detach == ((ORPHAN_HANDLE, True),)
    assert plan.raw == (sf.RawPatch(0, "u8", "0", "same byte"),)
    with pytest.raises(FrozenInstanceError):
        plan.money = 1  # type: ignore[misc]


def test_edit_plan_defaults_are_empty_immutable_tuples(synthetic_save: bytes) -> None:
    plan = EditPlan(source=_source(synthetic_save))

    assert plan.money is None
    assert plan.stacks == ()
    assert plan.moves == ()
    assert plan.detach == ()
    assert plan.attach == ()
    assert plan.raw == ()


def test_prepare_edit_rejects_stale_source_sha(synthetic_save: bytes) -> None:
    plan = EditPlan(
        source=_source(synthetic_save, sha256=hashlib.sha256(b"stale").hexdigest()),
        money=900_000,
    )

    with pytest.raises(sf.SaveError, match="SHA256"):
        prepare_edit(synthetic_save, plan)


def test_prepare_edit_rejects_raw_with_detach_before_patch_save(
    synthetic_save: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = EditPlan(
        source=_source(synthetic_save),
        detach=((STACK_HANDLE, False),),
        raw=(sf.RawPatch(0, "u8", "0", "test"),),
    )

    def unexpected_patch_save(*args: object, **kwargs: object) -> None:
        raise AssertionError("patch_save must not run for raw + detach")

    monkeypatch.setattr("editor.prepare.patch_save", unexpected_patch_save)
    with pytest.raises(sf.SaveError, match="raw.*detach|detach.*raw"):
        prepare_edit(synthetic_save, plan)


def test_prepare_edit_rejects_raw_with_attach_before_patch_save(
    synthetic_save: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = EditPlan(
        source=_source(synthetic_save),
        attach=((ORPHAN_HANDLE, 2, 0, 1, 1),),
        raw=(sf.RawPatch(0, "u8", "0", "test"),),
    )

    def unexpected_patch_save(*args: object, **kwargs: object) -> None:
        raise AssertionError("patch_save must not run for raw + attach")

    monkeypatch.setattr("editor.prepare.patch_save", unexpected_patch_save)
    with pytest.raises(sf.SaveError, match="raw.*attach|attach.*raw"):
        prepare_edit(synthetic_save, plan)


def test_prepare_edit_accepts_raw_only_and_returns_verified_bytes(
    synthetic_save: bytes,
) -> None:
    raw = sf.decompress_save(synthetic_save)
    offset = len(raw) - 1
    same_byte = raw[offset]
    plan = EditPlan(
        source=_source(synthetic_save),
        raw=(sf.RawPatch(offset, "u8", str(same_byte), "same byte"),),
    )

    prepared = prepare_edit(synthetic_save, plan)

    assert isinstance(prepared, PreparedEdit)
    assert prepared.plan is plan
    assert prepared.output_sha256 == hashlib.sha256(prepared.data).hexdigest()
    assert sf.decompress_save(prepared.data) == raw


def test_prepare_edit_accepts_detach_without_raw(synthetic_save: bytes) -> None:
    plan = EditPlan(source=_source(synthetic_save), detach=((STACK_HANDLE, False),))

    prepared = prepare_edit(synthetic_save, plan)

    info = sf.inspect_save(prepared.data)
    assert STACK_HANDLE not in {item.handle for item in info.inventory}
