"""Verify a public signed APT repository in an isolated apt state directory."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "SaveEditor-apt-verifier/1"})
    with urlopen(request, timeout=30) as response:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError(f"download failed: {url}")
        return response.read()


def _apt_options(root: Path, source_list: Path, keyring: Path) -> list[str]:
    state = root / "state"
    cache = root / "cache"
    (state / "lists" / "partial").mkdir(parents=True, exist_ok=True)
    (cache / "archives" / "partial").mkdir(parents=True, exist_ok=True)
    (state / "status").write_text("", encoding="utf-8")
    return [
        "-o",
        f"Dir::Etc::sourcelist={source_list}",
        "-o",
        "Dir::Etc::sourceparts=-",
        "-o",
        f"Dir::State={state}",
        "-o",
        f"Dir::State::status={state / 'status'}",
        "-o",
        f"Dir::State::lists={state / 'lists'}",
        "-o",
        f"Dir::Cache={cache}",
        "-o",
        "Dir::Cache::archives=archives",
        "-o",
        "Dir::Etc::trustedparts=-",
        "-o",
        "Dir::Etc::trusted=/dev/null",
        "-o",
        f"Dir::Etc::apt-keyparts={keyring.parent}",
        "-o",
        "Acquire::AllowInsecureRepositories=false",
        "-o",
        "Acquire::AllowDowngradeToInsecureRepositories=false",
    ]


def verify_repository(
    *,
    base_url: str,
    key_url: str,
    package: str = "stalker2-save-editor",
    version: str | None = None,
    distribution: str = "stable",
    component: str = "main",
) -> None:
    """Run apt update and prove that the published package is discoverable."""

    base_url = base_url.rstrip("/")
    with tempfile.TemporaryDirectory(prefix="save-editor-apt-") as temporary:
        root = Path(temporary)
        keyring = root / "repository-keyring.gpg"
        key_bytes = _download(key_url)
        subprocess.run(
            ["gpg", "--batch", "--dearmor", "--yes", "--output", str(keyring)],
            input=key_bytes,
            check=True,
        )
        source_list = root / "sources.list"
        source_list.write_text(
            f"deb [signed-by={keyring}] {base_url} {distribution} {component}\n",
            encoding="utf-8",
        )
        options = _apt_options(root, source_list, keyring)
        subprocess.run(["apt-get", *options, "-o", "Debug::NoLocking=true", "update"], check=True)
        policy = subprocess.run(
            ["apt-cache", *options, "policy", package],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if version is not None and f"Candidate: {version}" not in policy:
            raise RuntimeError(f"APT did not discover {package} version {version}:\n{policy}")
        if "Candidate:" not in policy or "Candidate: (none)" in policy:
            raise RuntimeError(f"APT has no candidate for {package}:\n{policy}")
        install_target = f"{package}={version}" if version else package
        download_dir = root / "download"
        download_dir.mkdir()
        subprocess.run(
            ["apt-get", *options, "download", install_target],
            check=True,
            cwd=download_dir,
        )
        if not list(download_dir.glob("*.deb")):
            raise RuntimeError(f"APT discovered {install_target} but did not download a package")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--key-url", required=True)
    parser.add_argument("--package", default="stalker2-save-editor")
    parser.add_argument("--version")
    parser.add_argument("--distribution", default="stable")
    parser.add_argument("--component", default="main")
    args = parser.parse_args(argv)
    try:
        verify_repository(
            base_url=args.base_url,
            key_url=args.key_url,
            package=args.package,
            version=args.version,
            distribution=args.distribution,
            component=args.component,
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(f"APT repository verified: {args.base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
