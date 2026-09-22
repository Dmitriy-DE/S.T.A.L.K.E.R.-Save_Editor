from __future__ import annotations

import hashlib
import json
from pathlib import Path

from test_s2_equipment_inventory import WEAPON_HANDLE, _save_with_grid_weapon

import save_format as sf
from editor.equipment import equipment_items, equipment_support_for_release
from editor.formats import STALKER2_FORMAT
from editor.models import EditPlan, SourceRef
from editor.service import EditorService
from web import web_bridge


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

    assert EditorService().inspect(synthetic_save) == expected

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

    replace_calls: list[tuple[Path, Path]] = []

    def replace(source: Path, value, backup: Path):
        replace_calls.append((source, backup))
        assert value is prepared
        return "replace-receipt"

    service = EditorService(export_fn=export, replace_fn=replace, upload_fn=upload)
    assert service.export_local(Path("source.sav"), tmp_path / "out.sav", prepared, tmp_path / "backup") == "export-receipt"
    assert export_calls == [(Path("source.sav"), tmp_path / "out.sav", tmp_path / "backup")]
    assert service.upload_cloud("worker", prepared, tmp_path / "backup", persisted_timeout=9) == "cloud-receipt"
    assert cloud_calls == [(tmp_path / "backup", 9)]
    assert service.replace_local(Path("source.sav"), prepared, tmp_path / "backup") == "replace-receipt"
    assert replace_calls == [(Path("source.sav"), tmp_path / "backup")]


def test_injected_inspect_and_prepare_do_not_require_registry_detection(
    synthetic_save: bytes,
) -> None:
    expected = sf.inspect_save(synthetic_save)
    calls: list[str] = []

    def inspect(_data: bytes, *, with_inventory: bool = True) -> sf.SaveInfo:
        calls.append(f"inspect:{with_inventory}")
        return expected

    def prepare(_data: bytes, _plan: EditPlan):
        calls.append("prepare")
        return "prepared"

    service = EditorService(inspect_fn=inspect, prepare_fn=prepare)
    fake_data = b"test-only injected bytes"

    assert service.inspect(fake_data) is expected
    assert service.prepare(fake_data, _plan(synthetic_save)) == "prepared"
    assert calls == ["inspect:True", "prepare"]


def test_service_restore_dependency_is_injectable(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path]] = []

    def restore(journal: Path, output: Path):
        calls.append((journal, output))
        return "restore-receipt"

    service = EditorService(restore_fn=restore)
    journal = tmp_path / "backup.json"
    output = tmp_path / "restored.sav"

    assert service.restore_local(journal, output) == "restore-receipt"
    assert calls == [(journal, output)]


def test_service_module_has_no_ui_imports() -> None:
    text = (Path(__file__).parents[1] / "editor" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "tkinter" not in text
    assert "PySide" not in text
    assert "PyQt" not in text


def test_web_and_desktop_use_the_same_release_equipment_projection(
    synthetic_save: bytes,
) -> None:
    data = _save_with_grid_weapon(synthetic_save)
    snapshot = json.loads(web_bridge.analyze(data, "weapon.sav"))
    info = STALKER2_FORMAT.inspect(data)

    desktop_rows = [
        row.as_dict()
        for row in equipment_items(info.inventory, release_id="stalker2")
    ]

    assert snapshot["equipment"] == desktop_rows
    assert snapshot["capabilities"]["equipment"] == equipment_support_for_release(
        "stalker2"
    ).as_dict()
    weapon = next(row for row in desktop_rows if row["handle"] == WEAPON_HANDLE)
    assert weapon["category"] == "weapon"
    assert weapon["modules"] == ["GunKharod_MagDefault", "HP_Laser_1"]
