from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import threading
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from editor import updater
from editor.update_manifest import ManifestError
from editor.updater import (
    UPDATE_USER_AGENT,
    InstallationInfo,
    UpdateClient,
    detect_installation,
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

    monkeypatch.setattr("editor.updater.urlopen", fake_urlopen)
    result = UpdateClient(
        manifest_url="https://download.example/latest.json",
        current_version="0.5.9",
        target="windows",
        allowed_hosts=frozenset({"download.example"}),
    ).check()

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


def test_wait_for_process_exit_returns_for_an_exited_process() -> None:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=2)
    updater.wait_for_process_exit(process.pid, timeout=0.5)
