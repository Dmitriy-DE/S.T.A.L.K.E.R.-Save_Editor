from __future__ import annotations

import hashlib
from pathlib import Path

import save_format as sf
from editor.models import EditPlan, SourceRef
from editor.service import EditorService


def _plan(data: bytes) -> EditPlan:
    return EditPlan(
        source=SourceRef(
            kind="local",
            locator="/tmp/synthetic-save.sav",
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        money=900_000,
    )


def test_service_prepare_matches_existing_patch_save(synthetic_save: bytes) -> None:
    service = EditorService()
    plan = _plan(synthetic_save)

    prepared = service.prepare(synthetic_save, plan)
    direct = sf.patch_save(synthetic_save, new_money=plan.money)

    assert prepared.plan is plan
    assert prepared.data == direct.data
    assert prepared.output_sha256 == hashlib.sha256(direct.data).hexdigest()


def test_service_inspect_and_dependencies_are_injectable(
    synthetic_save: bytes, tmp_path: Path
) -> None:
    calls: list[str] = []
    expected = sf.inspect_save(synthetic_save)

    def inspect(data: bytes, *, with_inventory: bool = True) -> sf.SaveInfo:
        calls.append(f"inspect:{with_inventory}")
        assert data == synthetic_save
        return expected

    service = EditorService(inspect_fn=inspect)
    assert service.inspect(synthetic_save, with_inventory=False) is expected
    assert calls == ["inspect:False"]

    plan = _plan(synthetic_save)
    prepared = service.prepare(synthetic_save, plan)
    export_calls: list[tuple[Path, Path, Path]] = []

    def export(source: Path, output: Path, value, backup: Path):
        export_calls.append((source, output, backup))
        assert value is prepared
        return "export-receipt"

    cloud_calls: list[tuple[Path, int]] = []

    def upload(worker, value, backup: Path, *, persisted_timeout: int, on_stage):
        cloud_calls.append((backup, persisted_timeout))
        assert value is prepared
        assert worker == "worker"
        return "cloud-receipt"

    service = EditorService(export_fn=export, upload_fn=upload)
    assert service.export_local(Path("source.sav"), tmp_path / "out.sav", prepared, tmp_path / "backup") == "export-receipt"
    assert export_calls == [(Path("source.sav"), tmp_path / "out.sav", tmp_path / "backup")]
    assert service.upload_cloud("worker", prepared, tmp_path / "backup", persisted_timeout=9) == "cloud-receipt"
    assert cloud_calls == [(tmp_path / "backup", 9)]


def test_service_module_has_no_ui_imports() -> None:
    text = (Path(__file__).parents[1] / "editor" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "tkinter" not in text
    assert "PySide" not in text
    assert "PyQt" not in text
