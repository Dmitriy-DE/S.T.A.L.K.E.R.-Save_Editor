from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools import build_ooz_encoder as encoder_build

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


def test_macos_target_requires_native_arm64_host() -> None:
    assert build.host_target("Darwin") == "macos"
    assert build.resolve_target("macos", host="Darwin", machine="arm64") == "macos"
    with pytest.raises(build.BuildError, match="arm64"):
        build.resolve_target("macos", host="Darwin", machine="x86_64")
    with pytest.raises(build.BuildError, match="не является cross-compiler"):
        build.resolve_target("macos", host="Linux", machine="arm64")


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
    assert build.artifact_names("9.9.9-test", "macos") == (
        "SaveEditor-macos-arm64-v9.9.9-test.zip",
        "SaveEditor-macos-arm64-v9.9.9-test.dmg",
    )


def test_desktop_shell_icons_are_bundled_with_the_application() -> None:
    spec_source = (ROOT / "packaging" / "editor.spec").read_text(encoding="utf-8")

    assert 'shell_icon_pack = ROOT / "assets" / "ui" / "shell_icons"' in spec_source
    assert 'datas.append((str(shell_icon_pack), "assets/ui/shell_icons"))' in spec_source
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


def test_encoder_setup_is_portable_and_uses_cxx11_on_macos(tmp_path: Path) -> None:
    source_root = tmp_path / "source" / "pyooz-0.0.8"
    ooz_root = source_root / "ooz" / "dep" / "ooz"
    ooz_root.joinpath("simde").mkdir(parents=True)
    for name in encoder_build._COMPRESSOR_SOURCES:
        (ooz_root / name).write_text("// fixture\n", encoding="utf-8")
    wrapper = tmp_path / "encoder_bindings.cpp"
    wrapper.write_text("// fixture\n", encoding="utf-8")

    macos_script = encoder_build._setup_script(
        source_root, wrapper, base_dir=tmp_path, target_platform="darwin"
    )
    windows_script = encoder_build._setup_script(
        source_root, wrapper, base_dir=tmp_path, target_platform="win32"
    )

    assert str(tmp_path) not in macos_script
    assert "encoder_bindings.cpp" in macos_script
    assert "source/pyooz-0.0.8" in macos_script
    assert 'extra_compile_args=["-std=c++11"]' in macos_script
    assert "-std=c++11" not in windows_script


def test_encoder_binding_imports_standard_math_for_msvc() -> None:
    binding = (ROOT / "third_party" / "pyooz" / "encoder_bindings.cpp").read_text(
        encoding="utf-8"
    )

    assert "#include <cmath>" in binding


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
    assert "required for changed compressed saves" in loaded["runtime_policy"]["encoder"]
    assert loaded["runtime_policy"]["steam_helper"] == "external executable; never bundled"


def test_macos_manifest_records_arm64_without_linux_libc(tmp_path: Path) -> None:
    manifest = build.build_manifest(root=ROOT, target="macos", version="test")

    assert manifest["architecture"] == "arm64"
    assert manifest["libc_minimum"] is None
    assert manifest["target"] == "macos"


def test_macos_package_helpers_use_native_bundle_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_icon = tmp_path / "icon.png"
    source_icon.write_bytes(b"png")
    bundle = tmp_path / "SaveEditor.app"
    bundle.mkdir()
    icon = tmp_path / "SaveEditor.icns"
    archive = tmp_path / "SaveEditor.zip"
    image = tmp_path / "SaveEditor.dmg"
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        Path(command[-1]).write_bytes(b"artifact")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(build.subprocess, "run", fake_run)

    build._generate_macos_icon(source_icon, icon)
    build._make_macos_zip(bundle, archive)
    build._make_macos_dmg(bundle, image, version="1.2.3")

    assert calls[0][:4] == ["sips", "-s", "format", "icns"]
    assert calls[0][4] == str(source_icon)
    assert calls[1][:5] == ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent"]
    assert calls[2][:2] == ["hdiutil", "create"]
    assert "-format" in calls[2] and "UDZO" in calls[2]
    assert all(path.is_file() for path in (icon, archive, image))


def test_macos_spec_declares_viewer_document_types_and_bundle_icon() -> None:
    source = (ROOT / "packaging" / "editor.spec").read_text(encoding="utf-8")

    assert "BUNDLE(" in source
    assert "CFBundleTypeRole" in source and "Viewer" in source
    assert '"sav"' in source and '"scop"' in source
    assert "SAVE_EDITOR_APP_ICON" in source
    assert "SAVE_EDITOR_BUILD_METADATA_DIR" in source


def test_macos_bundle_metadata_is_staged_for_pyinstaller_resources(tmp_path: Path) -> None:
    manifest = {
        "application": "SaveEditor",
        "version": "1.2.3",
        "source_commit": "abc123",
    }

    metadata_dir = build.stage_macos_bundle_metadata(tmp_path, manifest)

    assert json.loads((metadata_dir / "BUILD_MANIFEST.json").read_text(encoding="utf-8")) == manifest
    assert (metadata_dir / "SOURCE_COMMIT.txt").read_text(encoding="utf-8") == "abc123\n"


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


def test_public_linux_floor_is_explicit_and_release_gate_rejects_newer_hosts() -> None:
    assert build.SUPPORTED_GLIBC_BASELINE == "2.35"
    assert build.release_libc_requirement() == "2.35"
    with pytest.raises(build.BuildError, match="glibc baseline"):
        build.require_release_glibc("2.39")
    assert build.require_release_glibc("2.35.0") == "2.35"


def _deb_control(path: Path) -> dict[str, str]:
    result = subprocess.run(
        ["dpkg-deb", "-f", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    fields: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(": ")
        if separator:
            fields[key] = value
    return fields


@pytest.mark.skipif(shutil.which("dpkg-deb") is None, reason="dpkg-deb is required")
def test_debian_package_contains_real_desktop_appstream_and_runtime_metadata(tmp_path: Path) -> None:
    runtime = tmp_path / "SaveEditor"
    runtime.mkdir()
    executable = runtime / "SaveEditor"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    destination = tmp_path / "stalker2-save-editor_0.5.19_amd64.deb"

    build._build_deb(
        runtime=runtime,
        destination=destination,
        work=tmp_path / "work",
        version="0.5.19",
    )

    fields = _deb_control(destination)
    assert fields["Maintainer"]
    assert fields["Homepage"] == "https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor"
    assert fields["Section"] == "utils"
    assert fields["Description"].startswith("S.T.A.L.K.E.R. save editor")
    assert int(fields["Installed-Size"]) > 0
    assert "libc6 (>= " in fields["Depends"]
    for dependency in build.DEBIAN_RUNTIME_DEPENDENCIES:
        assert dependency in fields["Depends"]

    listing = subprocess.run(
        ["dpkg-deb", "-c", str(destination)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert f"Icon={build.DESKTOP_ID}" in build._desktop_entry()
    assert "com.github.dmitriyde.stalker2saveeditor.desktop" in listing
    assert "com.github.dmitriyde.stalker2saveeditor.metainfo.xml" in listing
    assert "com.github.dmitriyde.stalker2saveeditor.png" in listing
    assert "/usr/share/doc/stalker2-save-editor/copyright" in listing
    assert "/usr/share/man/man1/stalker2-save-editor.1.gz" in listing
    assert "/usr/share/doc/stalker2-save-editor/changelog.gz" in listing
    assert "/usr/share/lintian/overrides/stalker2-save-editor" in listing


@pytest.mark.skipif(shutil.which("appstreamcli") is None, reason="appstreamcli is required")
def test_appstream_metadata_validates_without_network() -> None:
    subprocess.run(
        [
            "appstreamcli",
            "validate",
            "--no-net",
            "--strict",
            str(ROOT / "packaging" / "com.github.dmitriyde.stalker2saveeditor.metainfo.xml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


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
