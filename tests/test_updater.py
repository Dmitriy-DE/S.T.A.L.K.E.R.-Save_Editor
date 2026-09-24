from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import threading
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from editor import updater
from editor.update_manifest import ManifestError
from editor.updater import (
    UPDATE_USER_AGENT,
    InstallationInfo,
    UpdateClient,
    build_installer_command,
    detect_installation,
    launch_installer,
    replace_installation,
    stage_archive,
)
from tools.build_release_manifest import build_release_manifest


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


@contextmanager
def _server(root: Path, manifest_payload: dict[str, object]) -> Iterator[str]:
    def handler(*args, **kwargs):
        return _QuietHandler(*args, directory=str(root), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    artifacts = manifest_payload["artifacts"]
    assert isinstance(artifacts, dict)
    all_artifacts = list(artifacts.values())
    optional = manifest_payload.get("optional_artifacts", {})
    if isinstance(optional, dict):
        all_artifacts.extend(optional.values())
    for artifact in all_artifacts:
        assert isinstance(artifact, dict)
        artifact["url"] = f"http://127.0.0.1:{port}/{artifact['file']}"
    (root / "latest.json").write_text(
        json.dumps(manifest_payload), encoding="utf-8"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/latest.json"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def _manifest_files(tmp_path: Path) -> dict[str, object]:
    files = {
        "windows-x86_64": tmp_path / "SaveEditor-windows-x86_64.zip",
        "windows-installer-x86_64": tmp_path / "SaveEditor-windows-x86_64-setup.exe",
        "linux-x86_64": tmp_path / "SaveEditor-linux-x86_64.tar.gz",
        "linux-deb-amd64": tmp_path / "stalker2-save-editor_amd64.deb",
    }
    files["windows-x86_64"].write_bytes(b"windows release bytes")
    files["windows-installer-x86_64"].write_bytes(b"windows installer bytes")
    files["linux-x86_64"].write_bytes(b"linux release bytes")
    files["linux-deb-amd64"].write_bytes(b"debian release bytes")
    output = tmp_path / "unused.json"
    return build_release_manifest(
        version="0.5.9",
        commit="d" * 40,
        artifacts=files,
        output=output,
        published_at="2026-09-20T12:00:00Z",
    )


def test_update_client_rejects_redirect_before_contacting_disallowed_host() -> None:
    target_hits: list[str] = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            target_hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_port = target.server_address[1]

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{target_port}/latest.json")
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirect_port = redirect.server_address[1]
    threads = [
        threading.Thread(target=target.serve_forever, daemon=True),
        threading.Thread(target=redirect.serve_forever, daemon=True),
    ]
    for thread in threads:
        thread.start()
    try:
        client = UpdateClient(
            manifest_url=f"http://127.0.0.1:{redirect_port}/latest.json",
            current_version="0.5.9",
            target="windows",
            allowed_hosts=frozenset({"127.0.0.1"}),
            allowed_schemes=frozenset({"http"}),
        )

        with pytest.raises(ManifestError, match="trusted download policy"):
            client._open(client.manifest_url)

        assert target_hits == []
    finally:
        redirect.shutdown()
        target.shutdown()
        for thread in threads:
            thread.join(timeout=2)
        redirect.server_close()
        target.server_close()


def test_update_client_reports_current_and_available_versions(tmp_path: Path) -> None:
    payload = _manifest_files(tmp_path)
    with _server(tmp_path, payload) as manifest_url:
        current = UpdateClient(
            manifest_url=manifest_url,
            current_version="0.5.9",
            target="windows",
            allowed_hosts=frozenset({"127.0.0.1"}),
            allowed_schemes=frozenset({"http"}),
        ).check()
        assert current.state == "current"

        available_payload = dict(payload)
        available_payload["version"] = "0.6.0"
        (tmp_path / "latest.json").write_text(json.dumps(available_payload), encoding="utf-8")
        available = UpdateClient(
            manifest_url=manifest_url,
            current_version="0.5.9",
            target="windows",
            allowed_hosts=frozenset({"127.0.0.1"}),
            allowed_schemes=frozenset({"http"}),
        ).check()
        assert available.state == "available"
        assert available.artifact is not None


def test_update_client_identifies_requests_to_public_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _manifest_files(tmp_path)
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, dict)
    for artifact in artifacts.values():
        assert isinstance(artifact, dict)
        artifact["url"] = f"https://download.example/{artifact['file']}"
    optional = payload.get("optional_artifacts", {})
    if isinstance(optional, dict):
        for artifact in optional.values():
            assert isinstance(artifact, dict)
            artifact["url"] = f"https://download.example/{artifact['file']}"
    body = json.dumps(payload).encode("utf-8")
    captured: dict[str, str | None] = {}

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://download.example/latest.json"

        def read(self, *_args: int) -> bytes:
            return body

    def fake_urlopen(request, *, timeout: float) -> _Response:
        captured["user_agent"] = request.get_header("User-agent")
        return _Response()

    client = UpdateClient(
        manifest_url="https://download.example/latest.json",
        current_version="0.5.9",
        target="windows",
        allowed_hosts=frozenset({"download.example"}),
    )
    monkeypatch.setattr(client._opener, "open", fake_urlopen)
    result = client.check()

    assert result.state == "current"
    assert captured["user_agent"] == UPDATE_USER_AGENT


def test_update_client_downloads_and_rejects_changed_bytes(tmp_path: Path) -> None:
    payload = _manifest_files(tmp_path)
    with _server(tmp_path, payload) as manifest_url:
        client = UpdateClient(
            manifest_url=manifest_url,
            current_version="0.5.0",
            target="windows",
            allowed_hosts=frozenset({"127.0.0.1"}),
            allowed_schemes=frozenset({"http"}),
        )
        result = client.check()
        assert result.artifact is not None
        destination = tmp_path / "downloaded.zip"
        assert client.download(result.artifact, destination) == destination
        assert destination.read_bytes() == b"windows release bytes"

        (tmp_path / "SaveEditor-windows-x86_64.zip").write_bytes(b"tampered bytes here")
        destination.unlink()
        with pytest.raises(ManifestError, match="mismatch"):
            client.download(result.artifact, destination)
        assert not destination.exists()

        # A body longer than the manifest size is cut off while downloading.
        (tmp_path / "SaveEditor-windows-x86_64.zip").write_bytes(b"x" * (result.artifact.size * 3))
        with pytest.raises(ManifestError, match="larger than the manifest size"):
            client.download(result.artifact, destination)
        assert not destination.exists()
        assert not list(tmp_path.glob(".downloaded.zip.*.part"))


def test_update_client_selects_windows_installer_artifact(tmp_path: Path) -> None:
    payload = _manifest_files(tmp_path)
    with _server(tmp_path, payload) as manifest_url:
        result = UpdateClient(
            manifest_url=manifest_url,
            current_version="0.5.0",
            target="windows",
            kind="installer",
            allowed_hosts=frozenset({"127.0.0.1"}),
            allowed_schemes=frozenset({"http"}),
        ).check()

    assert result.state == "available"
    assert result.artifact is not None
    assert result.artifact.kind == "installer"
    assert result.artifact.file == "SaveEditor-windows-x86_64-setup.exe"


def test_update_client_returns_unavailable_without_raising() -> None:
    result = UpdateClient(
        manifest_url="http://127.0.0.1:1/latest.json",
        current_version="0.5.8",
        target="windows",
        allowed_hosts=frozenset({"127.0.0.1"}),
        allowed_schemes=frozenset({"http"}),
        timeout=0.2,
    ).check()

    assert result.state == "unavailable"
    assert result.error


def test_detect_installation_reads_portable_manifest(tmp_path: Path) -> None:
    root = tmp_path / "SaveEditor"
    root.mkdir()
    executable = root / "SaveEditor.exe"
    executable.write_bytes(b"exe")
    (root / "BUILD_MANIFEST.json").write_text(
        json.dumps({"target": "windows", "architecture": "x86_64", "version": "0.5.9"}),
        encoding="utf-8",
    )

    info = detect_installation(executable=executable, platform_name="windows")

    assert info.kind == "portable"
    assert info.target == "windows"
    assert info.root == root


def test_detect_installation_reads_windows_installer_marker(tmp_path: Path) -> None:
    root = tmp_path / "SaveEditor"
    root.mkdir()
    executable = root / "SaveEditor.exe"
    executable.write_bytes(b"exe")
    (root / "BUILD_MANIFEST.json").write_text(
        json.dumps({"target": "windows", "architecture": "x86_64", "version": "0.5.9"}),
        encoding="utf-8",
    )
    (root / "INSTALLER_MARKER").write_text("installed", encoding="utf-8")

    info = detect_installation(executable=executable, platform_name="windows")

    assert info.kind == "installer"


def test_detect_installation_prefers_linux_package_root_with_build_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "usr" / "lib" / "stalker2-save-editor"
    package_root.mkdir(parents=True)
    executable = package_root / "SaveEditor"
    executable.write_bytes(b"app")
    (package_root / "BUILD_MANIFEST.json").write_text(
        json.dumps({"target": "linux", "architecture": "x86_64", "version": "0.5.9"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "PACKAGE_INSTALL_ROOT", package_root)

    info = detect_installation(executable=executable, platform_name="linux")

    assert info.kind == "package"
    assert info.root == package_root


def test_linux_package_handoff_prefers_pkexec_apt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    archive = tmp_path / "update.deb"
    archive.write_bytes(b"verified")
    installation = InstallationInfo("linux", "x86_64", "package", tmp_path, tmp_path / "SaveEditor")
    monkeypatch.setattr(updater.shutil, "which", lambda name: f"/usr/bin/{name}")

    command = build_installer_command(archive, installation, kind="package", platform_name="linux")

    assert command == ["/usr/bin/pkexec", "/usr/bin/apt-get", "install", "-y", str(archive.resolve())]


def test_launch_installer_returns_started_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    archive = tmp_path / "setup.exe"
    archive.write_bytes(b"verified")
    installation = InstallationInfo("windows", "x86_64", "installer", tmp_path, tmp_path / "SaveEditor.exe")
    calls: list[list[str]] = []

    class Process:
        pass

    def fake_popen(command, **kwargs):
        calls.append(command)
        assert kwargs["start_new_session"] is True
        return Process()

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)

    result = launch_installer(archive, installation, kind="installer", platform_name="windows")

    assert isinstance(result, Process)
    assert calls == [[str(archive.resolve())]]


def test_stage_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", "bad")

    installation = InstallationInfo("windows", "x86_64", "portable", tmp_path / "SaveEditor", tmp_path / "SaveEditor" / "SaveEditor.exe")
    with pytest.raises(ManifestError, match="path"):
        stage_archive(archive, installation, tmp_path / "stage")
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.parametrize("archive_kind", ("zip", "tar"))
def test_stage_archive_extracts_expected_application_tree(tmp_path: Path, archive_kind: str) -> None:
    archive = tmp_path / ("update.zip" if archive_kind == "zip" else "update.tar.gz")
    if archive_kind == "zip":
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("SaveEditor/SaveEditor.exe", "new executable")
            handle.writestr("SaveEditor/BUILD_MANIFEST.json", '{"target":"windows"}')
    else:
        with tarfile.open(archive, "w:gz") as handle:
            executable = tmp_path / "SaveEditor.exe"
            executable.write_text("new executable", encoding="utf-8")
            manifest = tmp_path / "BUILD_MANIFEST.json"
            manifest.write_text('{"target":"linux"}', encoding="utf-8")
            handle.add(executable, "SaveEditor/SaveEditor")
            handle.add(manifest, "SaveEditor/BUILD_MANIFEST.json")

    target = "windows" if archive_kind == "zip" else "linux"
    executable_name = "SaveEditor.exe" if target == "windows" else "SaveEditor"
    installation = InstallationInfo(
        target,
        "x86_64",
        "portable",
        tmp_path / "current",
        tmp_path / "current" / executable_name,
    )
    extracted = stage_archive(archive, installation, tmp_path / "stage")

    assert (extracted / executable_name).is_file()
    assert (extracted / "BUILD_MANIFEST.json").is_file()


def test_replace_installation_rolls_back_when_launcher_fails(tmp_path: Path) -> None:
    current = tmp_path / "SaveEditor"
    current.mkdir()
    (current / "SaveEditor.exe").write_text("old", encoding="utf-8")
    staged = tmp_path / "staged" / "SaveEditor"
    staged.mkdir(parents=True)
    (staged / "SaveEditor.exe").write_text("new", encoding="utf-8")
    installation = InstallationInfo("windows", "x86_64", "portable", current, current / "SaveEditor.exe")

    def fail_launcher(_path: Path) -> None:
        raise RuntimeError("new process failed")

    with pytest.raises(RuntimeError, match="new process"):
        replace_installation(staged, installation, launcher=fail_launcher)

    assert (current / "SaveEditor.exe").read_text(encoding="utf-8") == "old"
    assert not staged.exists()


def test_replace_installation_keeps_new_tree_when_backup_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = tmp_path / "SaveEditor"
    current.mkdir()
    (current / "SaveEditor.exe").write_text("old", encoding="utf-8")
    staged = tmp_path / "staged" / "SaveEditor"
    staged.mkdir(parents=True)
    (staged / "SaveEditor.exe").write_text("new", encoding="utf-8")
    installation = InstallationInfo(
        "windows",
        "x86_64",
        "portable",
        current,
        current / "SaveEditor.exe",
    )
    launched: list[Path] = []
    real_rmtree = updater.shutil.rmtree

    def fail_backup_cleanup(path, *args, **kwargs):
        candidate = Path(path)
        if candidate.name.startswith(".SaveEditor.backup-"):
            raise OSError("backup is temporarily locked")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(updater.shutil, "rmtree", fail_backup_cleanup)

    result = replace_installation(staged, installation, launcher=launched.append)

    assert result == current
    assert launched == [current / "SaveEditor.exe"]
    assert (current / "SaveEditor.exe").read_text(encoding="utf-8") == "new"
    backups = list(tmp_path.glob(".SaveEditor.backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "SaveEditor.exe").read_text(encoding="utf-8") == "old"


def test_wait_for_process_exit_returns_for_an_exited_process() -> None:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=2)
    updater.wait_for_process_exit(process.pid, timeout=0.5)
