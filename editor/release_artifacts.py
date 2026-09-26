"""Stable naming rules shared by builders and release publication tooling."""

from __future__ import annotations

APP_NAME = "SaveEditor"
DEBIAN_NAME = "stalker2-save-editor"


def debian_version(version: str) -> str:
    """Return a Debian-compatible version without inventing a release tag."""

    clean = "".join(ch if (ch.isalnum() or ch in ".+~-") else "-" for ch in version)
    if not clean or not clean[0].isdigit():
        clean = f"0+{clean}"
    return clean


def artifact_names(version: str, target: str) -> tuple[str, ...]:
    if target == "linux":
        return (
            f"{APP_NAME}-linux-x86_64-v{version}.tar.gz",
            f"{DEBIAN_NAME}_{debian_version(version)}_amd64.deb",
        )
    if target == "windows":
        return (
            f"{APP_NAME}-windows-x86_64-v{version}.zip",
            f"{APP_NAME}-windows-x86_64-v{version}-setup.exe",
        )
    if target == "macos":
        return (
            f"{APP_NAME}-macos-arm64-v{version}.zip",
            f"{APP_NAME}-macos-arm64-v{version}.dmg",
        )
    raise ValueError(f"unknown build target: {target}")


__all__ = ["APP_NAME", "DEBIAN_NAME", "artifact_names", "debian_version"]
