from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("save_editor_build", ROOT / "packaging" / "build.py")
assert SPEC and SPEC.loader
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def test_resolve_target_rejects_cross_os_build() -> None:
    assert build.resolve_target("auto", host="Linux") == "linux"
    assert build.resolve_target("windows", host="Windows") == "windows"
    with pytest.raises(build.BuildError, match="не является cross-compiler"):
        build.resolve_target("windows", host="Linux")


def test_artifact_names_include_architecture_and_version() -> None:
    assert build.artifact_names("9.9.9-test", "linux") == (
        "SaveEditor-linux-x86_64-v9.9.9-test.tar.gz",
        "stalker2-save-editor_9.9.9-test_amd64.deb",
    )
    assert build.artifact_names("9.9.9-test", "windows") == (
        "SaveEditor-windows-x86_64-v9.9.9-test.zip",
    )


def test_scan_package_tree_rejects_private_inputs(tmp_path: Path) -> None:
    safe = tmp_path / "safe.txt"
    safe.write_text("ok", encoding="utf-8")
    build.scan_package_tree(tmp_path)
    (tmp_path / "copied.sav").write_bytes(b"private")
    with pytest.raises(build.BuildError, match="private input"):
        build.scan_package_tree(tmp_path)
    (tmp_path / "copied.sav").unlink()
    (tmp_path / "credentials.json").write_text("private", encoding="utf-8")
    with pytest.raises(build.BuildError, match="private input"):
        build.scan_package_tree(tmp_path)


def test_manifest_is_machine_readable_and_declares_runtime_policy(tmp_path: Path) -> None:
    manifest = build.build_manifest(root=ROOT, target="linux", version="test")
    path = tmp_path / "BUILD_MANIFEST.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["architecture"] == "x86_64"
    assert loaded["runtime_policy"]["core"] == "Python standard library"
    assert loaded["runtime_policy"]["steam_helper"] == "external executable; never bundled"


def test_plan_is_explicitly_non_cross_compiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build, "host_target", lambda system=None: "linux")
    result = build.plan(target="linux", output_dir=tmp_path, version="9.9.9-test")
    assert result["cross_compile"] is False
    assert result["artifacts"][0].endswith(".tar.gz")


def test_debian_dependency_tracks_the_build_host_libc() -> None:
    assert build.libc_requirement("2.39") == "2.39"
    assert build.libc_requirement("2.35.0") == "2.35"
    assert build.libc_requirement("") == build.FALLBACK_LIBC_VERSION
    assert build.libc_requirement("unknown") == build.FALLBACK_LIBC_VERSION
    manifest = build.build_manifest(root=ROOT, target="linux", version="test")
    assert manifest["libc_minimum"] == build.libc_requirement()
    assert build.build_manifest(root=ROOT, target="windows", version="test")["libc_minimum"] is None


def test_build_refuses_to_start_without_working_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Usage:
        free = 100 * 1024**2

    monkeypatch.setattr(build.shutil, "disk_usage", lambda _path: _Usage())
    with pytest.raises(build.BuildError, match="Недостаточно места"):
        build._require_free_space(tmp_path)


def test_build_accepts_a_filesystem_with_room(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Usage:
        free = build.MIN_FREE_BYTES

    monkeypatch.setattr(build.shutil, "disk_usage", lambda _path: _Usage())
    build._require_free_space(tmp_path)


def test_manifest_does_not_call_its_own_output_a_dirty_source(tmp_path: Path) -> None:
    # The CI build writes into artifacts/ inside the checkout, which made every
    # manifest report source_dirty=true for the build's own products.
    output_dir = ROOT / "artifacts"
    commit, dirty = build._git_state(ROOT, ignore=output_dir)
    assert commit
    assert not any(entry == "artifacts" or entry.startswith("artifacts/") for entry in dirty)

    outside = build._git_state(ROOT, ignore=tmp_path)
    assert isinstance(outside[1], tuple)


def test_pyinstaller_spec_bundles_generated_official_catalog() -> None:
    spec = (ROOT / "packaging" / "editor.spec").read_text(encoding="utf-8")

    assert 'ROOT / "web" / "catalogs.json"' in spec
    assert 'datas.append((str(catalog_path), "web"))' in spec
