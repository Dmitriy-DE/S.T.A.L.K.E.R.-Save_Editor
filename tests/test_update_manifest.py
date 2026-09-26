from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from editor.update_manifest import (
    ArtifactSpec,
    ManifestError,
    ReleaseManifest,
    compare_versions,
)


def _artifact_payload(
    *,
    target: str = "windows-x86_64",
    architecture: str = "x86_64",
    kind: str = "portable",
    file: str = "SaveEditor-windows-x86_64.zip",
    body: bytes = b"release bytes",
    url: str = "https://save-editor-downloads.save-editor.workers.dev/SaveEditor-windows-x86_64.zip",
) -> dict[str, object]:
    return {
        "target": target,
        "architecture": architecture,
        "kind": kind,
        "file": file,
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "url": url,
    }


def _manifest_payload() -> dict[str, object]:
    body = _artifact_payload()
    installer_body = _artifact_payload(
        target="windows-installer-x86_64",
        kind="installer",
        file="SaveEditor-windows-x86_64-setup.exe",
        body=b"installer bytes",
        url="https://save-editor-downloads.save-editor.workers.dev/SaveEditor-windows-x86_64-setup.exe",
    )
    linux_body = _artifact_payload(
        target="linux-x86_64",
        file="SaveEditor-linux-x86_64.tar.gz",
        body=b"linux bytes",
        url="https://save-editor-downloads.save-editor.workers.dev/SaveEditor-linux-x86_64.tar.gz",
    )
    deb_body = _artifact_payload(
        target="linux-deb-amd64",
        kind="package",
        file="stalker2-save-editor_amd64.deb",
        body=b"deb bytes",
        url="https://save-editor-downloads.save-editor.workers.dev/stalker2-save-editor_amd64.deb",
    )
    macos_body = _artifact_payload(
        target="macos-arm64",
        architecture="arm64",
        kind="disk-image",
        file="SaveEditor-macos-arm64.dmg",
        body=b"macOS disk image bytes",
        url="https://save-editor-downloads.save-editor.workers.dev/SaveEditor-macos-arm64.dmg",
    )
    return {
        "schema": 1,
        "channel": "stable",
        "version": "0.5.9",
        "source_commit": "a" * 40,
        "published_at": "2026-09-20T12:00:00Z",
        "artifacts": {
            "windows-x86_64": body,
            "linux-x86_64": linux_body,
            "linux-deb-amd64": deb_body,
        },
        "optional_artifacts": {
            "windows-installer-x86_64": installer_body,
            "macos-arm64": macos_body,
        },
    }


def test_manifest_parses_and_selects_portable_targets() -> None:
    manifest = ReleaseManifest.from_json(json.dumps(_manifest_payload()))

    assert manifest.version == "0.5.9"
    assert manifest.select("windows").file == "SaveEditor-windows-x86_64.zip"
    assert manifest.select("windows", kind="installer").file == "SaveEditor-windows-x86_64-setup.exe"
    assert manifest.select("linux").file == "SaveEditor-linux-x86_64.tar.gz"
    assert manifest.select("linux", kind="package").file == "stalker2-save-editor_amd64.deb"
    assert manifest.select("macos", "arm64", kind="disk-image").file == (
        "SaveEditor-macos-arm64.dmg"
    )
    with pytest.raises(ManifestError, match="artifact not available"):
        manifest.select("macos", "x86_64", kind="disk-image")


def test_manifest_rejects_unknown_target_and_bad_schema() -> None:
    manifest = ReleaseManifest.from_json(json.dumps(_manifest_payload()))

    with pytest.raises(ManifestError, match="artifact not available"):
        manifest.select("darwin")

    payload = _manifest_payload()
    payload["schema"] = 2
    with pytest.raises(ManifestError, match="schema"):
        ReleaseManifest.from_json(json.dumps(payload))


def test_manifest_rejects_mismatched_macos_artifact_kind() -> None:
    payload = _manifest_payload()
    optional = payload["optional_artifacts"]
    assert isinstance(optional, dict)
    macos_artifact = optional["macos-arm64"]
    assert isinstance(macos_artifact, dict)
    macos_artifact["kind"] = "portable"

    manifest = ReleaseManifest.from_json(json.dumps(payload))

    with pytest.raises(ManifestError, match="artifact not available"):
        manifest.select("macos", "arm64", kind="disk-image")


@pytest.mark.parametrize(
    ("current", "latest", "expected"),
    (("0.5.8", "0.5.8", 0), ("0.5.8", "0.5.9", -1), ("0.6.0", "0.5.9", 1)),
)
def test_compare_versions_orders_numeric_versions(current: str, latest: str, expected: int) -> None:
    assert compare_versions(current, latest) == expected


def test_compare_versions_rejects_ambiguous_versions() -> None:
    with pytest.raises(ManifestError, match="version"):
        compare_versions("v0.5.8", "0.5.9")


def test_manifest_rejects_non_r2_url() -> None:
    payload = _manifest_payload()
    windows = payload["artifacts"]["windows-x86_64"]
    assert isinstance(windows, dict)
    windows["url"] = "https://example.invalid/update.zip"

    with pytest.raises(ManifestError, match="download host"):
        ReleaseManifest.from_json(json.dumps(payload))


def test_artifact_verify_checks_size_and_sha256(tmp_path: Path) -> None:
    path = tmp_path / "artifact.zip"
    path.write_bytes(b"release bytes")
    artifact = ArtifactSpec.from_payload(_artifact_payload())

    artifact.verify(path)

    path.write_bytes(b"tampered")
    with pytest.raises(ManifestError, match="size mismatch"):
        artifact.verify(path)

    path.write_bytes(b"tampered data")
    with pytest.raises(ManifestError, match="SHA-256"):
        artifact.verify(path)
