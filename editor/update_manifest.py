"""Validated release metadata shared by the updater and release tooling."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

MANIFEST_SCHEMA = 1
DOWNLOAD_HOST = "save-editor-downloads.save-editor.workers.dev"
DOWNLOAD_BASE_URL = f"https://{DOWNLOAD_HOST}"
SUPPORTED_ARTIFACTS = (
    "windows-x86_64",
    "linux-x86_64",
    "linux-deb-amd64",
)
OPTIONAL_ARTIFACTS = ("windows-installer-x86_64",)
_VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """Raised when release metadata cannot be trusted or consumed."""


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{field} must be a non-empty string")
    return value


def _parse_version(value: str) -> tuple[tuple[int, int, int], tuple[tuple[int, object], ...]]:
    match = _VERSION_RE.fullmatch(value)
    if match is None:
        raise ManifestError(f"invalid version: {value!r}")
    core = tuple(int(part) for part in match.group(0).split("-", 1)[0].split("."))
    prerelease = match.group(4)
    identifiers: list[tuple[int, object]] = []
    if prerelease is not None:
        for identifier in prerelease.split("."):
            if identifier.isdigit():
                if len(identifier) > 1 and identifier.startswith("0"):
                    raise ManifestError(f"invalid version: {value!r}")
                identifiers.append((0, int(identifier)))
            else:
                identifiers.append((1, identifier))
    return (core[0], core[1], core[2]), tuple(identifiers)


def compare_versions(current: str, latest: str) -> int:
    """Compare strict semver-like ``MAJOR.MINOR.PATCH`` release versions."""

    current_core, current_pre = _parse_version(current)
    latest_core, latest_pre = _parse_version(latest)
    if current_core != latest_core:
        return (current_core > latest_core) - (current_core < latest_core)
    if not current_pre and not latest_pre:
        return 0
    if not current_pre:
        return 1
    if not latest_pre:
        return -1
    for left, right in zip(current_pre, latest_pre, strict=False):
        if left != right:
            return (left > right) - (left < right)
    return (len(current_pre) > len(latest_pre)) - (len(current_pre) < len(latest_pre))


@dataclass(frozen=True)
class ArtifactSpec:
    """One immutable, hash-addressed downloadable release artifact."""

    target: str
    architecture: str
    kind: str
    file: str
    size: int
    sha256: str
    url: str

    @classmethod
    def from_payload(
        cls,
        payload: object,
        *,
        allowed_hosts: frozenset[str] = frozenset({DOWNLOAD_HOST}),
        allowed_schemes: frozenset[str] = frozenset({"https"}),
    ) -> ArtifactSpec:
        if not isinstance(payload, dict):
            raise ManifestError("artifact must be an object")
        target = _require_string(payload.get("target"), "artifact.target")
        architecture = _require_string(payload.get("architecture"), "artifact.architecture")
        kind = _require_string(payload.get("kind"), "artifact.kind")
        file = _require_string(payload.get("file"), "artifact.file")
        sha256 = _require_string(payload.get("sha256"), "artifact.sha256")
        url = _require_string(payload.get("url"), "artifact.url")
        size = payload.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ManifestError("artifact.size must be a non-negative integer")
        if "/" in file or "\\" in file or file in {".", ".."}:
            raise ManifestError("artifact.file must be a plain filename")
        if not _SHA256_RE.fullmatch(sha256):
            raise ManifestError("artifact.sha256 must be lowercase SHA-256")
        parsed = urlparse(url)
        if (
            parsed.scheme not in allowed_schemes
            or parsed.hostname not in allowed_hosts
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ManifestError("artifact download host or URL is not trusted")
        if parsed.path != f"/{file}":
            raise ManifestError("artifact URL does not match artifact filename")
        if kind not in {"portable", "package", "installer"}:
            raise ManifestError("artifact.kind is unsupported")
        return cls(target, architecture, kind, file, size, sha256, url)

    def to_payload(self) -> dict[str, object]:
        return {
            "target": self.target,
            "architecture": self.architecture,
            "kind": self.kind,
            "file": self.file,
            "size": self.size,
            "sha256": self.sha256,
            "url": self.url,
        }

    def verify(self, path: Path) -> None:
        """Verify a downloaded file before it is extracted or installed."""

        if not path.is_file():
            raise ManifestError(f"artifact is missing: {path}")
        actual_size = path.stat().st_size
        if actual_size != self.size:
            raise ManifestError(
                f"artifact size mismatch: expected {self.size}, got {actual_size}"
            )
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual_sha = digest.hexdigest()
        if actual_sha != self.sha256:
            raise ManifestError(
                f"artifact SHA-256 mismatch: expected {self.sha256}, got {actual_sha}"
            )


@dataclass(frozen=True)
class ReleaseManifest:
    """A validated stable-channel release manifest."""

    schema: int
    channel: str
    version: str
    source_commit: str
    published_at: str
    artifacts: dict[str, ArtifactSpec]

    @classmethod
    def from_json(
        cls,
        payload: str,
        *,
        allowed_hosts: frozenset[str] = frozenset({DOWNLOAD_HOST}),
        allowed_schemes: frozenset[str] = frozenset({"https"}),
    ) -> ReleaseManifest:
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"manifest JSON is invalid: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ManifestError("manifest must be an object")
        if value.get("schema") != MANIFEST_SCHEMA:
            raise ManifestError("unsupported manifest schema")
        if value.get("channel") != "stable":
            raise ManifestError("unsupported release channel")
        version = _require_string(value.get("version"), "version")
        _parse_version(version)
        source_commit = _require_string(value.get("source_commit"), "source_commit")
        if not re.fullmatch(r"[0-9a-f]{40,64}", source_commit):
            raise ManifestError("source_commit must be a lowercase Git SHA")
        published_at = _require_string(value.get("published_at"), "published_at")
        raw_artifacts = value.get("artifacts")
        if not isinstance(raw_artifacts, dict):
            raise ManifestError("artifacts must be an object")
        if not set(SUPPORTED_ARTIFACTS).issubset(raw_artifacts):
            raise ManifestError("manifest artifacts are incomplete")
        artifacts: dict[str, ArtifactSpec] = {}
        for key in SUPPORTED_ARTIFACTS:
            artifact = ArtifactSpec.from_payload(
                raw_artifacts[key],
                allowed_hosts=allowed_hosts,
                allowed_schemes=allowed_schemes,
            )
            if artifact.target != key:
                raise ManifestError(f"artifact target does not match key: {key}")
            artifacts[key] = artifact
        raw_optional = value.get("optional_artifacts", {})
        if not isinstance(raw_optional, dict):
            raise ManifestError("optional_artifacts must be an object")
        unknown_optional = set(raw_optional) - set(OPTIONAL_ARTIFACTS)
        if unknown_optional:
            raise ManifestError("optional_artifacts contains an unsupported target")
        for key in OPTIONAL_ARTIFACTS:
            if key not in raw_optional:
                continue
            artifact = ArtifactSpec.from_payload(
                raw_optional[key],
                allowed_hosts=allowed_hosts,
                allowed_schemes=allowed_schemes,
            )
            if artifact.target != key:
                raise ManifestError(f"artifact target does not match key: {key}")
            artifacts[key] = artifact
        return cls(MANIFEST_SCHEMA, "stable", version, source_commit, published_at, artifacts)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": self.schema,
            "channel": self.channel,
            "version": self.version,
            "source_commit": self.source_commit,
            "published_at": self.published_at,
            "artifacts": {key: self.artifacts[key].to_payload() for key in SUPPORTED_ARTIFACTS},
        }
        optional = {
            key: self.artifacts[key].to_payload()
            for key in OPTIONAL_ARTIFACTS
            if key in self.artifacts
        }
        if optional:
            payload["optional_artifacts"] = optional
        return payload

    def select(
        self,
        target: str,
        architecture: str = "x86_64",
        *,
        kind: str = "portable",
    ) -> ArtifactSpec:
        if target == "windows" and kind == "portable":
            key = "windows-x86_64"
        elif target == "windows" and kind == "installer":
            key = "windows-installer-x86_64"
        elif target == "linux" and kind == "portable":
            key = "linux-x86_64"
        elif target == "linux" and kind == "package":
            key = "linux-deb-amd64"
        else:
            raise ManifestError(f"artifact not available for target={target!r}, kind={kind!r}")
        artifact = self.artifacts.get(key)
        if artifact is None or artifact.architecture != architecture:
            raise ManifestError(f"artifact not available for target={target!r}")
        return artifact


__all__ = [
    "DOWNLOAD_BASE_URL",
    "DOWNLOAD_HOST",
    "MANIFEST_SCHEMA",
    "OPTIONAL_ARTIFACTS",
    "SUPPORTED_ARTIFACTS",
    "ArtifactSpec",
    "ManifestError",
    "ReleaseManifest",
    "compare_versions",
]
