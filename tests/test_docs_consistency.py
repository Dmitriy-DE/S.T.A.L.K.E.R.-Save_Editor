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
    assert "editor/equipment_matrix.py" in bundle.MODULES
    assert "editor/xray_delete.py" in bundle.MODULES
    assert bundle.main(["--check"]) == 0, (
        "web/pysrc.json is stale; run python3 tools/build_web_bundle.py"
    )
    assert theme.main(["--check"]) == 0, (
        "web/theme.css is stale; run python3 tools/export_theme.py"
    )


def test_theme_export_reads_the_canonical_palette_assignment() -> None:
    import tools.export_theme as theme

    palette = theme.read_palette()

    assert palette["bg_base"] == "#0C0D0A"
    assert palette["text"] == "#D8D2BE"


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


def test_equipment_matrix_is_linked_and_keeps_enhanced_editions_fail_closed() -> None:
    root = Path(__file__).parents[1]
    readme = (root / "docs" / "README.md").read_text(encoding="utf-8")
    matrix = (root / "docs" / "evidence" / "EQUIPMENT_SUPPORT_MATRIX_2026-09-22.md").read_text(
        encoding="utf-8"
    )

    assert "EQUIPMENT_SUPPORT_MATRIX_2026-09-22.md" in readme
    assert "Enhanced Edition" in matrix
    assert "unsupported" in matrix
    assert "NVG" in matrix and "binocular" in matrix


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


def test_web_bundle_ships_every_core_module_the_bridge_imports() -> None:
    """A module missing from the bundle breaks the page at start-up."""

    import ast

    import tools.build_web_bundle as bundle

    root = Path(__file__).resolve().parents[1]
    shipped = set(bundle.MODULES)
    pending = ["web/web_bridge.py", "save_format.py"]
    seen: set[str] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse((root / path).read_text(encoding="utf-8"))
        package = path.rsplit("/", 1)[0] if path.startswith("editor/") else "editor"
        # Module-level imports only: lazy imports inside functions are guarded
        # and never run in the browser (preferences, platforms).
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                if node.level == 1:
                    module = f"{package}/{(node.module or '').replace('.', '/')}"
                elif node.module and node.module.startswith("editor"):
                    module = node.module.replace(".", "/")
                else:
                    continue
                names = [module] + [f"{module}/{alias.name}" for alias in node.names]
            elif isinstance(node, ast.Import):
                names = [alias.name.replace(".", "/") for alias in node.names if alias.name.startswith("editor")]
            else:
                continue
            for name in names:
                candidate = f"{name}.py"
                if (root / candidate).is_file():
                    pending.append(candidate)
    missing = sorted(path for path in seen if path.startswith("editor/") and path not in shipped)
    assert missing == [], f"add to tools/build_web_bundle.py MODULES: {missing}"
