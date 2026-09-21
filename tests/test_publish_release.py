from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request

import pytest

from tools.publish_release import main, prepare_release, publish_r2, verify_public_r2


def _versioned_artifacts(root: Path, version: str = "0.5.9") -> Path:
    artifacts = root / "artifacts"
    artifacts.mkdir()
    (artifacts / f"SaveEditor-windows-x86_64-v{version}.zip").write_bytes(b"windows bytes")
    (artifacts / f"SaveEditor-windows-x86_64-v{version}-setup.exe").write_bytes(b"installer bytes")
    (artifacts / f"SaveEditor-linux-x86_64-v{version}.tar.gz").write_bytes(b"linux bytes")
    (artifacts / f"stalker2-save-editor_{version}_amd64.deb").write_bytes(b"deb bytes")
    return artifacts


def test_publish_release_cli_imports_from_repository_root() -> None:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / "tools" / "publish_release.py"), "--help"],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Prepare and publish" in result.stdout


def test_prepare_release_creates_exact_stable_files_and_manifest(tmp_path: Path) -> None:
    artifacts = _versioned_artifacts(tmp_path)
    output = tmp_path / "release"

    result = prepare_release(
        artifact_dir=artifacts,
        output_dir=output,
        version="0.5.9",
        commit="e" * 40,
        published_at="2026-09-20T12:00:00Z",
    )

    assert result["manifest"] == output / "latest.json"
    windows = output / "SaveEditor-windows-x86_64.zip"
    assert windows.read_bytes() == b"windows bytes"
    installer = output / "SaveEditor-windows-x86_64-setup.exe"
    assert installer.read_bytes() == b"installer bytes"
    manifest = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["windows-x86_64"]["sha256"] == hashlib.sha256(
        b"windows bytes"
    ).hexdigest()
    assert manifest["optional_artifacts"]["windows-installer-x86_64"]["sha256"] == hashlib.sha256(
        b"installer bytes"
    ).hexdigest()
    assert (output / "SHA256SUMS").read_text(encoding="utf-8").count("\n") == 4


def test_prepare_release_rejects_missing_versioned_artifact(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    with pytest.raises(ValueError, match="missing"):
        prepare_release(
            artifact_dir=artifacts,
            output_dir=tmp_path / "release",
            version="0.5.9",
            commit="f" * 40,
            published_at="2026-09-20T12:00:00Z",
        )


def test_publish_r2_uses_stable_keys_and_explicit_wrangler_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = _versioned_artifacts(tmp_path)
    output = tmp_path / "release"
    prepare_release(
        artifact_dir=artifacts,
        output_dir=output,
        version="0.5.9",
        commit="1" * 40,
        published_at="2026-09-20T12:00:00Z",
    )
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("tools.publish_release.subprocess.run", fake_run)
    publish_r2(output, runner="npx", wrangler_version="4")

    assert len(commands) == 6
    assert all("r2" in command and "object" in command and "put" in command for command in commands)
    assert any("save-editor-downloads/latest.json" in command for command in commands)
    assert any("save-editor-downloads/SaveEditor-windows-x86_64.zip" in command for command in commands)
    assert any("save-editor-downloads/SaveEditor-windows-x86_64-setup.exe" in command for command in commands)
    assert any("save-editor-downloads/SHA256SUMS" in command for command in commands)
    assert "save-editor-downloads/latest.json" in commands[-1]


def test_prepared_mode_publishes_without_regenerating_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = _versioned_artifacts(tmp_path)
    output = tmp_path / "release"
    prepare_release(
        artifact_dir=artifacts,
        output_dir=output,
        version="0.5.9",
        commit="3" * 40,
        published_at="2026-09-20T12:00:00Z",
    )
    manifest_before = (output / "latest.json").read_bytes()
    calls: list[tuple[str, Path]] = []

    def reject_prepare(**_kwargs: object) -> dict[str, Path]:
        raise AssertionError("prepared publication must not rebuild latest.json")

    def fake_publish(root: Path) -> None:
        calls.append(("publish", root))

    def fake_verify(root: Path, *, base_url: str) -> None:
        assert base_url
        calls.append(("verify", root))

    monkeypatch.setattr("tools.publish_release.prepare_release", reject_prepare)
    monkeypatch.setattr("tools.publish_release.publish_r2", fake_publish)
    monkeypatch.setattr("tools.publish_release.verify_public_r2", fake_verify)

    assert main(["--output", str(output), "--prepared", "--publish-r2", "--verify-r2"]) == 0
    assert calls == [("publish", output.resolve()), ("verify", output.resolve())]
    assert (output / "latest.json").read_bytes() == manifest_before


def test_verify_public_r2_identifies_itself_to_the_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = _versioned_artifacts(tmp_path)
    output = tmp_path / "release"
    prepare_release(
        artifact_dir=artifacts,
        output_dir=output,
        version="0.5.9",
        commit="2" * 40,
        published_at="2026-09-20T12:00:00Z",
    )
    bodies = {path.name: path.read_bytes() for path in output.iterdir() if path.is_file()}

    class _Response:
        status = 200

        def __init__(self, body: bytes) -> None:
            self.headers = {"Content-Length": str(len(body))}
            self._body = body

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return self._body

    def fake_urlopen(request: Request, *, timeout: float) -> _Response:
        assert request.get_header("User-agent") == "SaveEditor-release-verifier/1"
        filename = Path(urlparse(request.full_url).path).name
        return _Response(bodies[filename])

    monkeypatch.setattr("tools.publish_release.urlopen", fake_urlopen)
    verify_public_r2(output, base_url="https://downloads.example")


def test_download_worker_treats_manifest_as_json_and_binary_files_as_attachments() -> None:
    worker = (Path(__file__).parents[1] / "infra" / "downloads-worker" / "worker.js").read_text(
        encoding="utf-8"
    )

    assert 'key === "latest.json"' in worker
    assert 'application/json; charset=utf-8' in worker
    assert 'content-disposition", "inline"' in worker
    assert 'attachment; filename=' in worker


def test_download_worker_accepts_bounded_diagnostics_without_public_read_access() -> None:
    worker = (Path(__file__).parents[1] / "infra" / "downloads-worker" / "worker.js").read_text(
        encoding="utf-8"
    )

    assert 'pathname === "/diagnostics"' in worker
    assert 'request.method !== "POST"' in worker
    assert 'application/gzip' in worker
    assert "MAX_DIAGNOSTIC_BYTES" in worker
    assert 'diagnostics/${' in worker
    assert "env.BUCKET.put" in worker
    assert "DIAGNOSTICS_RATE_LIMITER" in worker
    assert "cleanupDiagnostics" not in worker
    assert "bucket.list" not in worker
    assert "bucket.delete" not in worker
    assert 'key.startsWith("diagnostics/")' in worker


def test_download_worker_retention_and_rate_limit_are_declarative() -> None:
    root = Path(__file__).parents[1]
    worker = (root / "infra" / "downloads-worker" / "worker.js").read_text(encoding="utf-8")
    config = (root / "infra" / "downloads-worker" / "wrangler.toml").read_text(encoding="utf-8")
    lifecycle = json.loads(
        (root / "infra" / "downloads-worker" / "lifecycle.json").read_text(encoding="utf-8")
    )

    assert "DIAGNOSTICS_RATE_LIMITER" in worker
    assert "scheduled" not in worker
    assert "ctx.waitUntil(cleanupDiagnostics" not in worker
    assert '[[ratelimits]]' in config
    assert 'name = "DIAGNOSTICS_RATE_LIMITER"' in config
    assert lifecycle == {
        "Rules": [
            {
                "ID": "diagnostics-retention",
                "Status": "Enabled",
                "Filter": {"Prefix": "diagnostics/"},
                "Expiration": {"Days": 30},
            }
        ]
    }
