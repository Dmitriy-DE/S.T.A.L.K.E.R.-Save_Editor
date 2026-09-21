from __future__ import annotations

import gzip
import hashlib
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from tools.build_apt_repo import build_repository
from tools.verify_apt_repo import verify_repository


def _make_package(root: Path, version: str = "0.5.19") -> Path:
    stage = root / "stage"
    (stage / "DEBIAN").mkdir(parents=True)
    (stage / "DEBIAN" / "control").write_text(
        """Package: stalker2-save-editor
Version: 0.5.19
Section: games
Priority: optional
Architecture: amd64
Maintainer: Test <test@example.invalid>
Depends: libc6
Description: Test Save Editor package
 A package used by the repository index test.
""",
        encoding="utf-8",
    )
    (stage / "usr" / "bin").mkdir(parents=True)
    (stage / "usr" / "bin" / "stalker2-save-editor").write_text("#!/bin/sh\n", encoding="utf-8")
    package = root / "stalker2-save-editor_0.5.19_amd64.deb"
    subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(stage), str(package)], check=True)
    return package


def _make_keyring(root: Path) -> tuple[Path, str]:
    home = root / "gnupg"
    home.mkdir(mode=0o700)
    batch = root / "key.batch"
    batch.write_text(
        """%no-protection
Key-Type: RSA
Key-Length: 2048
Name-Real: Save Editor Test
Name-Email: save-editor-test@example.invalid
Expire-Date: 0
%commit
""",
        encoding="utf-8",
    )
    environment = {"GNUPGHOME": str(home)}
    subprocess.run(["gpg", "--batch", "--generate-key", str(batch)], check=True, env=environment)
    result = subprocess.run(
        ["gpg", "--batch", "--list-secret-keys", "--with-colons"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    key_id = next(
        field.split(":")[9]
        for field in result.stdout.splitlines()
        if field.startswith("fpr:")
    )
    return home, key_id


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Debian repository integration requires the POSIX dpkg and APT toolchain",
)
def test_build_repository_creates_signed_debian_layout(tmp_path: Path) -> None:
    package = _make_package(tmp_path)
    gpg_home, key_id = _make_keyring(tmp_path)
    output = tmp_path / "apt"

    files = build_repository(
        package=package,
        output=output,
        signing_key=key_id,
        gpg_home=gpg_home,
        source_date_epoch=1_758_000_000,
    )

    package_name = package.name
    copied = output / "pool" / "main" / "s" / "stalker2-save-editor" / package_name
    packages = output / "dists" / "stable" / "main" / "binary-amd64" / "Packages"
    assert copied.read_bytes() == package.read_bytes()
    assert packages.is_file()
    assert (packages.with_suffix(".gz")).is_file()
    assert (output / "dists" / "stable" / "Release").is_file()
    assert (output / "dists" / "stable" / "InRelease").is_file()
    assert (output / "dists" / "stable" / "Release.gpg").is_file()
    assert (output / "repository-key.asc").is_file()
    assert copied.relative_to(output).as_posix() in packages.read_text(encoding="utf-8")
    assert hashlib.sha256(package.read_bytes()).hexdigest() in packages.read_text(encoding="utf-8")
    release = (output / "dists" / "stable" / "Release").read_text(encoding="utf-8")
    assert " main/binary-amd64/Packages\n" in release
    assert " dists/stable/main/binary-amd64/Packages\n" not in release
    assert gzip.decompress((packages.with_suffix(".gz")).read_bytes()) == packages.read_bytes()
    assert set(files) >= {"repository-key.asc", "dists/stable/InRelease"}

    handler = partial(SimpleHTTPRequestHandler, directory=str(output))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        verify_repository(
            base_url=base_url,
            key_url=f"{base_url}/repository-key.asc",
            version="0.5.19",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
