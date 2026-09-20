from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tools.publish_release import prepare_release, publish_r2


def _versioned_artifacts(root: Path, version: str = "0.5.9") -> Path:
    artifacts = root / "artifacts"
    artifacts.mkdir()
    (artifacts / f"SaveEditor-windows-x86_64-v{version}.zip").write_bytes(b"windows bytes")
    (artifacts / f"SaveEditor-linux-x86_64-v{version}.tar.gz").write_bytes(b"linux bytes")
    (artifacts / f"stalker2-save-editor_{version}_amd64.deb").write_bytes(b"deb bytes")
    return artifacts


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
    manifest = json.loads((output / "latest.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["windows-x86_64"]["sha256"] == hashlib.sha256(
        b"windows bytes"
    ).hexdigest()
    assert (output / "SHA256SUMS").read_text(encoding="utf-8").count("\n") == 3


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

    assert len(commands) == 4
    assert all("r2" in command and "object" in command and "put" in command for command in commands)
    assert any("save-editor-downloads/latest.json" in command for command in commands)
    assert any("save-editor-downloads/SaveEditor-windows-x86_64.zip" in command for command in commands)


def test_download_worker_treats_manifest_as_json_and_binary_files_as_attachments() -> None:
    worker = (Path(__file__).parents[1] / "infra" / "downloads-worker" / "worker.js").read_text(
        encoding="utf-8"
    )

    assert 'key === "latest.json"' in worker
    assert 'application/json; charset=utf-8' in worker
    assert 'content-disposition", "inline"' in worker
    assert 'attachment; filename=' in worker
