"""The task queue must have exactly one source of truth.

docs/tasks/INDEX.md used to be maintained by hand next to tasks.json, and the
two had already started to disagree.  The table in INDEX.md is now generated
from tasks.json; these tests fail when it drifts or when a card goes missing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.render_task_index as render


def _tasks() -> list[dict[str, object]]:
    return json.loads(render.TASKS_JSON.read_text(encoding="utf-8"))


def test_index_table_is_generated_from_tasks_json() -> None:
    assert render.main(["--check"]) == 0, (
        "docs/tasks/INDEX.md is stale; run python3 tools/render_task_index.py"
    )


def test_every_task_has_a_card_and_a_unique_id() -> None:
    tasks = _tasks()
    ids = [task["id"] for task in tasks]
    assert len(ids) == len(set(ids))
    for task in tasks:
        card = Path(render.ROOT) / str(task["path"])
        assert card.is_file(), f"missing card for {task['id']}: {task['path']}"


def test_dependencies_reference_known_tasks() -> None:
    tasks = _tasks()
    known = {task["id"] for task in tasks}
    for task in tasks:
        for dependency in task.get("depends_on") or []:
            assert dependency in known, f"{task['id']} depends on unknown {dependency}"


@pytest.mark.parametrize("field", ["status", "title", "gate", "priority"])
def test_required_fields_are_present(field: str) -> None:
    for task in _tasks():
        assert task.get(field), f"{task['id']} has no {field}"


def test_status_values_are_from_the_documented_set() -> None:
    allowed = {"ready", "waiting_dependencies", "in_progress", "in_review", "accepted", "blocked"}
    for task in _tasks():
        assert task["status"] in allowed, f"{task['id']} has status {task['status']!r}"


def test_web_bundle_and_theme_are_generated_from_the_sources() -> None:
    import tools.build_web_bundle as bundle
    import tools.export_theme as theme

    assert "editor/capabilities.py" in bundle.MODULES
    assert "editor/equipment.py" in bundle.MODULES
    assert "editor/xray_delete.py" in bundle.MODULES
    assert bundle.main(["--check"]) == 0, (
        "web/pysrc.json is stale; run python3 tools/build_web_bundle.py"
    )
    assert theme.main(["--check"]) == 0, (
        "web/theme.css is stale; run python3 tools/export_theme.py"
    )


def test_cross_platform_spec_records_equipment_evidence_boundary() -> None:
    document = (render.ROOT / "docs" / "specs" / "CROSS_PLATFORM_EDITOR.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "Equipment",
        "weapon",
        "armor",
        "helmet",
        "S2",
        "game load/re-save",
        "read-only",
    ):
        assert marker in document


def test_release_docs_record_portable_updates_and_r2_contract() -> None:
    root = render.ROOT
    readme = (root / "README.md").read_text(encoding="utf-8")
    release = (root / "docs" / "RELEASE.md").read_text(encoding="utf-8")
    for document in (readme, release):
        for marker in (
            "Windows portable",
            "Linux portable",
            "latest.json",
            "Cloudflare R2",
            "SHA-256",
            "автообнов",
        ):
            assert marker.casefold() in document.casefold(), marker
    assert "make release-manifest" in readme
    assert "--publish-r2" in release


def test_download_page_exposes_separate_windows_installer_and_portable_links() -> None:
    page = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")

    assert 'id="dl-windows-installer"' in page
    assert 'id="dl-windows-portable"' in page
    assert "SaveEditor-windows-x86_64-setup.exe" in page
    assert "SaveEditor-windows-x86_64.zip" in page


def test_browser_catalog_is_compact_official_metadata_only() -> None:
    catalog_path = render.ROOT / "web" / "catalogs.json"
    document = json.loads(catalog_path.read_text(encoding="utf-8"))

    assert document["schema_version"] == 1
    releases = document["releases"]
    assert set(releases) == {"stalker-soc", "stalker-cs", "stalker-cop"}
    allowed_families = {
        "ammo",
        "base",
        "detector",
        "document",
        "outfit",
        "pda",
        "torch",
        "weapon",
        "weapon_magazined",
        "weapon_shotgun",
        "weapon_wgl",
    }
    for release in releases.values():
        assert release["source"] == "official-resource-metadata"
        assert release["items"]
        for item in release["items"]:
            assert set(item) == {
                "category",
                "key",
                "max_stack",
                "serialization_family",
                "display_name",
                "icon_x",
                "icon_y",
                "icon_texture",
            }
            assert item["key"]
            assert item["serialization_family"] in allowed_families
            assert item["display_name"] is None or isinstance(item["display_name"], str)
            assert item["icon_x"] is None or isinstance(item["icon_x"], int)
            assert item["icon_y"] is None or isinstance(item["icon_y"], int)
            assert item["icon_texture"] is None or isinstance(item["icon_texture"], str)
            assert all(
                suffix not in item["key"].casefold()
                for suffix in (".sav", ".scop", ".scs", ".bak", ".db")
            )
