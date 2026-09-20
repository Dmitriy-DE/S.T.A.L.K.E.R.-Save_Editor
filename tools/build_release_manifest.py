"""Build a stable release manifest from final artifact bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Keep ``python tools/build_release_manifest.py`` usable as a direct entry
# point, just like the release publisher that imports this module.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from editor.update_manifest import (
    DOWNLOAD_BASE_URL,
    MANIFEST_SCHEMA,
    OPTIONAL_ARTIFACTS,
    SUPPORTED_ARTIFACTS,
)

_ARTIFACT_METADATA = {
    "windows-x86_64": ("portable", "x86_64", "SaveEditor-windows-x86_64.zip"),
    "windows-installer-x86_64": (
        "installer",
        "x86_64",
        "SaveEditor-windows-x86_64-setup.exe",
    ),
    "linux-x86_64": ("portable", "x86_64", "SaveEditor-linux-x86_64.tar.gz"),
    "linux-deb-amd64": ("package", "x86_64", "stalker2-save-editor_amd64.deb"),
}


def _sha256(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def build_release_manifest(
    *,
    version: str,
    commit: str,
    artifacts: dict[str, Path],
    output: Path,
    published_at: str,
) -> dict[str, object]:
    missing = set(SUPPORTED_ARTIFACTS) - set(artifacts)
    if missing:
        raise ValueError(f"artifacts missing required targets: {sorted(missing)}")
    if not commit or any(ch not in "0123456789abcdef" for ch in commit) or len(commit) < 40:
        raise ValueError("commit must be a lowercase Git SHA")
    def describe(target: str) -> dict[str, object]:
        path = Path(artifacts[target]).resolve()
        if not path.is_file():
            raise ValueError(f"artifact is missing: {path}")
        kind, architecture, filename = _ARTIFACT_METADATA[target]
        size, sha256 = _sha256(path)
        return {
            "target": target,
            "architecture": architecture,
            "kind": kind,
            "file": filename,
            "size": size,
            "sha256": sha256,
            "url": f"{DOWNLOAD_BASE_URL}/{filename}",
        }

    payload_artifacts: dict[str, dict[str, object]] = {}
    for target in SUPPORTED_ARTIFACTS:
        payload_artifacts[target] = describe(target)
    optional_payload: dict[str, dict[str, object]] = {}
    for target in OPTIONAL_ARTIFACTS:
        if target in artifacts:
            optional_payload[target] = describe(target)
    payload: dict[str, object] = {
        "schema": MANIFEST_SCHEMA,
        "channel": "stable",
        "version": version,
        "source_commit": commit,
        "published_at": published_at,
        "artifacts": payload_artifacts,
    }
    if optional_payload:
        payload["optional_artifacts"] = optional_payload
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _artifact_argument(value: str) -> tuple[str, Path]:
    target, separator, path = value.partition("=")
    supported = {*SUPPORTED_ARTIFACTS, *OPTIONAL_ARTIFACTS}
    if not separator or target not in supported or not path:
        raise argparse.ArgumentTypeError("ожидалось target=PATH для поддержанного artifact target")
    return target, Path(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--published-at", default=datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    parser.add_argument("--artifact", action="append", type=_artifact_argument, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = build_release_manifest(
            version=args.version,
            commit=args.commit,
            artifacts=dict(args.artifact),
            output=args.output,
            published_at=args.published_at,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
