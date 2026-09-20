from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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


def test_builder_script_plan_runs_from_repository_root() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "packaging" / "build.py"), "--plan"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"cross_compile": false' in result.stdout


def test_artifact_names_include_architecture_and_version() -> None:
    assert build.artifact_names("9.9.9-test", "linux") == (
        "SaveEditor-linux-x86_64-v9.9.9-test.tar.gz",
        "stalker2-save-editor_9.9.9-test_amd64.deb",
    )
    assert build.artifact_names("9.9.9-test", "windows") == (
        "SaveEditor-windows-x86_64-v9.9.9-test.zip",
        "SaveEditor-windows-x86_64-v9.9.9-test-setup.exe",
    )


def test_windows_installer_script_is_built_from_the_packaged_runtime() -> None:
    script = build._windows_installer_script()

    assert "SAVE_EDITOR_RUNTIME" in script
    assert "SAVE_EDITOR_OUTPUT" in script
    assert "SaveEditor.exe" in script
    assert "PrivilegesRequired=admin" in script


def test_windows_installer_build_uses_inno_and_requires_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "SaveEditor"
    runtime.mkdir()
    destination = tmp_path / "SaveEditor-windows-x86_64-v0.5.14-setup.exe"
    compiler = tmp_path / "ISCC.exe"
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        Path(str(environment["SAVE_EDITOR_OUTPUT"]))
        destination.write_bytes(b"installer")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(build, "_find_inno_compiler", lambda: compiler)
    monkeypatch.setattr(build.subprocess, "run", fake_run)

    result = build._build_windows_installer(
        runtime=runtime,
        destination=destination,
        work=tmp_path / "work",
        version="0.5.14",
    )

    assert result == destination
    assert destination.read_bytes() == b"installer"
    assert calls and calls[0][0] == str(compiler)


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
