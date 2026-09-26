from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.build_release_manifest import build_release_manifest


def test_build_release_manifest_uses_final_bytes_and_stable_urls(tmp_path: Path) -> None:
    windows = tmp_path / "windows.zip"
    installer = tmp_path / "windows-setup.exe"
    linux = tmp_path / "linux.tar.gz"
    deb = tmp_path / "editor.deb"
    macos = tmp_path / "SaveEditor-macos-arm64.dmg"
    windows.write_bytes(b"windows final bytes")
    installer.write_bytes(b"installer final bytes")
    linux.write_bytes(b"linux final bytes")
    deb.write_bytes(b"deb final bytes")
    macos.write_bytes(b"macOS disk image bytes")
    output = tmp_path / "latest.json"

    payload = build_release_manifest(
        version="0.5.9",
        commit="b" * 40,
        artifacts={
            "windows-x86_64": windows,
            "windows-installer-x86_64": installer,
            "linux-x86_64": linux,
            "linux-deb-amd64": deb,
            "macos-arm64": macos,
        },
        output=output,
        published_at="2026-09-20T12:00:00Z",
    )

    assert output.is_file()
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded == payload
    assert loaded["artifacts"]["windows-x86_64"]["size"] == len(b"windows final bytes")
    assert loaded["artifacts"]["windows-x86_64"]["sha256"] == hashlib.sha256(
        b"windows final bytes"
    ).hexdigest()
    assert loaded["artifacts"]["linux-deb-amd64"]["file"] == "stalker2-save-editor_amd64.deb"
    assert loaded["optional_artifacts"]["windows-installer-x86_64"]["size"] == len(
        b"installer final bytes"
    )
    assert loaded["optional_artifacts"]["macos-arm64"] == {
        "target": "macos-arm64",
        "architecture": "arm64",
        "kind": "disk-image",
        "file": "SaveEditor-macos-arm64.dmg",
        "size": len(b"macOS disk image bytes"),
        "sha256": hashlib.sha256(b"macOS disk image bytes").hexdigest(),
        "url": "https://save-editor-downloads.save-editor.workers.dev/SaveEditor-macos-arm64.dmg",
    }


def test_build_release_manifest_requires_all_targets(tmp_path: Path) -> None:
    windows = tmp_path / "windows.zip"
    windows.write_bytes(b"windows")

    try:
        build_release_manifest(
            version="0.5.9",
            commit="c" * 40,
            artifacts={"windows-x86_64": windows},
            output=tmp_path / "latest.json",
            published_at="2026-09-20T12:00:00Z",
        )
    except ValueError as exc:
        assert "artifacts" in str(exc)
    else:  # pragma: no cover - the assertion documents the required failure
        raise AssertionError("missing release targets were accepted")
