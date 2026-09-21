"""Build a small signed APT repository for the Debian release artifact."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from email.utils import format_datetime
from pathlib import Path

DEFAULT_DISTRIBUTION = "stable"
DEFAULT_COMPONENT = "main"
DEFAULT_ARCHITECTURE = "amd64"
PACKAGE_NAME = "stalker2-save-editor"


def _run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"required command is missing: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout).strip()
        raise RuntimeError(f"command failed ({exc.returncode}): {' '.join(command)}: {detail}") from exc


def _control_fields(package: Path) -> dict[str, str]:
    result = _run(["dpkg-deb", "-f", str(package)])
    fields: dict[str, str] = {}
    current: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith((" ", "\t")) and current is not None:
            fields[current] += "\n" + line
            continue
        name, separator, value = line.partition(": ")
        if not separator:
            continue
        current = name
        fields[name] = value
    return fields


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _index_stanza(*, package: Path, fields: dict[str, str], filename: str) -> str:
    required = ("Package", "Version", "Architecture", "Maintainer", "Description")
    missing = [name for name in required if not fields.get(name)]
    if missing:
        raise ValueError(f"Debian package is missing control fields: {', '.join(missing)}")
    lines = [
        f"{name}: {fields[name]}"
        for name in (
            "Package",
            "Version",
            "Architecture",
            "Maintainer",
            "Installed-Size",
            "Section",
            "Priority",
            "Depends",
            "Recommends",
            "Suggests",
            "Homepage",
            "Description",
        )
        if fields.get(name)
    ]
    lines.extend(
        (
            f"Filename: {filename}",
            f"Size: {package.stat().st_size}",
            f"MD5sum: {_digest(package, 'md5')}",
            f"SHA1: {_digest(package, 'sha1')}",
            f"SHA256: {_sha256(package)}",
        )
    )
    return "\n".join(lines) + "\n"


def _gzip_deterministic(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as compressed:
        compressed.write(data)
    return buffer.getvalue()


def _write_release(
    *,
    release_path: Path,
    distribution: str,
    component: str,
    architecture: str,
    source_date_epoch: int,
    relative_files: list[str],
) -> None:
    date = format_datetime(datetime.fromtimestamp(source_date_epoch, tz=UTC), usegmt=True)
    lines = [
        "Origin: S.T.A.L.K.E.R. Save Editor",
        "Label: S.T.A.L.K.E.R. Save Editor",
        f"Suite: {distribution}",
        f"Codename: {distribution}",
        f"Date: {date}",
        f"Architectures: {architecture}",
        f"Components: {component}",
        "Description: Signed Debian repository for S.T.A.L.K.E.R. Save Editor",
    ]
    checksums: dict[str, list[tuple[str, int, str]]] = {"MD5Sum": [], "SHA1": [], "SHA256": []}
    for relative in relative_files:
        path = release_path.parent / relative
        checksums["MD5Sum"].append((_digest(path, "md5"), path.stat().st_size, relative))
        checksums["SHA1"].append((_digest(path, "sha1"), path.stat().st_size, relative))
        checksums["SHA256"].append((_sha256(path), path.stat().st_size, relative))
    for label in ("MD5Sum", "SHA1", "SHA256"):
        lines.append(f"{label}:")
        lines.extend(f" {digest} {size:16d} {relative}" for digest, size, relative in checksums[label])
    release_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gpg_environment(gpg_home: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["GNUPGHOME"] = str(gpg_home)
    return environment


def build_repository(
    *,
    package: Path,
    output: Path,
    signing_key: str,
    gpg_home: Path,
    distribution: str = DEFAULT_DISTRIBUTION,
    component: str = DEFAULT_COMPONENT,
    architecture: str = DEFAULT_ARCHITECTURE,
    source_date_epoch: int | None = None,
) -> list[str]:
    """Create a signed repository and return its relative files."""

    package = Path(package).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    gpg_home = Path(gpg_home).expanduser().resolve()
    if not package.is_file():
        raise ValueError(f"Debian package is missing: {package}")
    fields = _control_fields(package)
    if fields.get("Package") != PACKAGE_NAME:
        raise ValueError(f"unexpected Debian package name: {fields.get('Package')!r}")
    if fields.get("Architecture") != architecture:
        raise ValueError(f"unexpected Debian architecture: {fields.get('Architecture')!r}")
    if not signing_key:
        raise ValueError("APT signing key is required")
    if source_date_epoch is None:
        source_date_epoch = int(os.environ.get("SOURCE_DATE_EPOCH", int(time.time())))

    pool_relative = Path("pool") / component / PACKAGE_NAME[0] / PACKAGE_NAME / package.name
    pool_path = output / pool_relative
    pool_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(package, pool_path)
    index_relative = Path("dists") / distribution / component / f"binary-{architecture}" / "Packages"
    index_path = output / index_relative
    index_path.parent.mkdir(parents=True, exist_ok=True)
    stanza = _index_stanza(package=pool_path, fields=fields, filename=pool_relative.as_posix())
    index_path.write_text(stanza, encoding="utf-8")
    compressed_path = index_path.with_suffix(index_path.suffix + ".gz")
    compressed_path.write_bytes(_gzip_deterministic(stanza.encode("utf-8")))

    release_path = output / "dists" / distribution / "Release"
    release_path.parent.mkdir(parents=True, exist_ok=True)
    relative_files = [
        index_path.relative_to(release_path.parent).as_posix(),
        compressed_path.relative_to(release_path.parent).as_posix(),
    ]
    _write_release(
        release_path=release_path,
        distribution=distribution,
        component=component,
        architecture=architecture,
        source_date_epoch=source_date_epoch,
        relative_files=relative_files,
    )
    environment = _gpg_environment(gpg_home)
    gpg_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    detached_signature = release_path.with_name("Release.gpg")
    inrelease = release_path.with_name("InRelease")
    _run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--local-user",
            signing_key,
            "--detach-sign",
            "--output",
            str(detached_signature),
            str(release_path),
        ],
        env=environment,
    )
    _run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--local-user",
            signing_key,
            "--clearsign",
            "--output",
            str(inrelease),
            str(release_path),
        ],
        env=environment,
    )
    public_key = _run(["gpg", "--batch", "--armor", "--export", signing_key], env=environment).stdout
    (output / "repository-key.asc").write_text(public_key, encoding="utf-8")

    return sorted(
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signing-key", required=True)
    parser.add_argument("--gpg-home", type=Path, required=True)
    parser.add_argument("--distribution", default=DEFAULT_DISTRIBUTION)
    parser.add_argument("--component", default=DEFAULT_COMPONENT)
    parser.add_argument("--architecture", default=DEFAULT_ARCHITECTURE)
    parser.add_argument("--source-date-epoch", type=int)
    args = parser.parse_args(argv)
    try:
        files = build_repository(
            package=args.package,
            output=args.output,
            signing_key=args.signing_key,
            gpg_home=args.gpg_home,
            distribution=args.distribution,
            component=args.component,
            architecture=args.architecture,
            source_date_epoch=args.source_date_epoch,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print("\n".join(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
