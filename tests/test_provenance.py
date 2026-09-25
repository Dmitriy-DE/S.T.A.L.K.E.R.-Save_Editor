from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_provenance.py"
_BASES = {"own", "ofl", "game-derived", "wiki-cc-by-sa", "fextralife"}
_FIELDS = {"source", "origin_url", "basis", "generator"}


def _asset_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for folder in (root / "assets", root / "web" / "icons")
        if folder.exists()
        for path in folder.rglob("*")
        if path.is_file()
    }


def _assert_manifest_covers_tree(root: Path) -> dict[str, dict[str, object]]:
    manifest_path = root / "assets" / "PROVENANCE.json"
    assert manifest_path.is_file(), "assets/PROVENANCE.json has not been generated"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)

    files = _asset_files(root)
    covered_by: dict[str, list[str]] = {path: [] for path in files}
    for pattern, entry in manifest.items():
        assert isinstance(pattern, str)
        assert isinstance(entry, dict)
        assert set(entry) == _FIELDS
        assert isinstance(entry["source"], str) and entry["source"]
        assert isinstance(entry["origin_url"], str) and entry["origin_url"].startswith("https://")
        assert entry["basis"] in _BASES
        assert entry["generator"] is None or isinstance(entry["generator"], str)

        matches = [
            path.relative_to(root).as_posix()
            for path in root.glob(pattern)
            if path.is_file()
        ]
        assert matches, f"manifest record has no matching file: {pattern}"
        for path in matches:
            covered_by[path].append(pattern)

    assert set(covered_by) == files
    assert all(len(patterns) == 1 for patterns in covered_by.values())
    return manifest


def _write_file(root: Path, relative_path: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture", encoding="utf-8")


def test_committed_provenance_manifest_covers_all_assets_without_extra_records() -> None:
    manifest = _assert_manifest_covers_tree(ROOT)

    assert "assets/PROVENANCE.json" in manifest
    assert "assets/icons/xray/*.png" in manifest
    assert "web/icons/*.png" in manifest


def test_builder_covers_each_asset_pack_and_omits_empty_records(tmp_path: Path) -> None:
    for path in (
        "assets/app_icon.svg",
        "assets/app_icon_64.png",
        "assets/chrome/xray/frame.png",
        "assets/fonts/Oswald[wght].ttf",
        "assets/icons/xray/example.png",
        "assets/icons/xray/index.json",
        "assets/icons/s2/example.png",
        "assets/icons/s2/Medkit.png",
        "assets/readme/hero.svg",
        "assets/ui/item_glyphs/armor.svg",
        "assets/ui/s2_shell/preview_zone.png",
        "web/icons/example.png",
        "web/icons/index.json",
        "web/icons/s2/example.png",
        "web/icons/s2/Medkit.png",
    ):
        _write_file(tmp_path, path)

    source_map = tmp_path / "data" / "s2_sources.json"
    source_map.parent.mkdir(parents=True)
    source_map.write_text(
        json.dumps(
            {
                "consumables": {
                    "Medkit": [
                        "Medkit",
                        "https://static0.fextralifeimages.com/file/stalker2/medkit.png",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(BUILDER), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    manifest = _assert_manifest_covers_tree(tmp_path)
    assert "assets/icons/s2/example.png" in manifest
    assert "web/icons/s2/example.png" in manifest
    assert manifest["assets/icons/s2/Medkit.png"]["basis"] == "fextralife"
    assert manifest["web/icons/s2/Medkit.png"]["basis"] == "fextralife"
    assert manifest["assets/icons/s2/Medkit.png"]["origin_url"] == (
        "https://static0.fextralifeimages.com/file/stalker2/medkit.png"
    )
    assert "assets/chrome/xray/*.png" in manifest
