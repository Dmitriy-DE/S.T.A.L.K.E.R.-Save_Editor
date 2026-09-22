"""Build the optional native Kraken encoder from the vendored pyooz source."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


class EncoderBuildError(RuntimeError):
    """Raised when the release encoder cannot be built safely."""


_COMPRESSOR_SOURCES = (
    "bitknit.cpp",
    "lzna.cpp",
    "kraken.cpp",
    "compress.cpp",
    "compr_entropy.cpp",
    "compr_kraken.cpp",
    "compr_leviathan.cpp",
    "compr_match_finder.cpp",
    "compr_mermaid.cpp",
    "compr_multiarray.cpp",
    "compr_tans.cpp",
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != destination and destination not in target.parents:
            raise EncoderBuildError(f"Небезопасный путь в pyooz archive: {member.name}")
        archive.extract(member, destination)


def _source_root(work: Path, archive_path: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        _safe_extract(archive, work)
    candidates = sorted(
        path for path in work.iterdir() if path.is_dir() and path.name.startswith("pyooz-")
    )
    if len(candidates) != 1:
        raise EncoderBuildError("В pyooz source archive не найден единственный source root")
    return candidates[0]


def _setup_script(source_root: Path, wrapper: Path) -> str:
    ooz_root = source_root / "ooz" / "dep" / "ooz"
    sources = [wrapper, *(ooz_root / name for name in _COMPRESSOR_SOURCES)]
    missing = [path for path in sources if not path.is_file()]
    if missing:
        raise EncoderBuildError(
            "В pyooz source archive отсутствуют encoder sources: "
            + ", ".join(str(path) for path in missing)
        )
    encoded_sources = json.dumps([str(path) for path in sources])
    encoded_include = json.dumps([str(source_root), str(ooz_root / "simde")])
    return f"""from setuptools import Extension, setup

setup(
    name='save-editor-ooz-encoder',
    version='0.0.0',
    ext_modules=[Extension(
        name='ooz_encoder',
        sources={encoded_sources},
        include_dirs={encoded_include},
        define_macros=[('Py_LIMITED_API', '0x03080000')],
        py_limited_api=True,
    )],
)
"""


def build_encoder(
    *,
    root: Path | None = None,
    output_dir: Path,
    python_executable: str | None = None,
) -> Path:
    """Compile ``ooz_encoder`` into ``output_dir`` and return its extension path."""

    root = (root or _repository_root()).resolve()
    archive_path = root / "third_party" / "pyooz" / "pyooz-0.0.8.tar.gz"
    wrapper = root / "third_party" / "pyooz" / "encoder_bindings.cpp"
    if not archive_path.is_file():
        raise EncoderBuildError(f"pyooz source archive отсутствует: {archive_path}")
    if not wrapper.is_file():
        raise EncoderBuildError(f"encoder binding отсутствует: {wrapper}")

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="save-editor-ooz-", dir=output_dir.parent
    ) as raw_work:
        work = Path(raw_work)
        source_root = _source_root(work / "source", archive_path)
        setup_path = work / "setup.py"
        setup_path.write_text(_setup_script(source_root, wrapper), encoding="utf-8")
        build_temp = work / "build"
        interpreter = (
            str(Path(python_executable).expanduser().resolve())
            if python_executable is not None
            else sys.executable
        )
        command = [interpreter, str(setup_path)]
        command.extend(
            ("build_ext", "--build-lib", str(output_dir), "--build-temp", str(build_temp))
        )
        try:
            subprocess.run(command, cwd=work, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise EncoderBuildError(f"Сборка ooz_encoder завершилась ошибкой: {exc}") from exc

    candidates = tuple(
        path
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name.startswith("ooz_encoder")
        and path.suffix.lower() in {".so", ".pyd", ".dll"}
    )
    if len(candidates) != 1:
        raise EncoderBuildError(
            f"Сборка ooz_encoder не создала ровно один extension: {candidates!r}"
        )
    return candidates[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Save Editor Kraken encoder")
    parser.add_argument("--root", type=Path, default=_repository_root())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--python")
    args = parser.parse_args(argv)
    try:
        result = build_encoder(
            root=args.root,
            output_dir=args.output_dir,
            python_executable=args.python,
        )
    except EncoderBuildError as exc:
        print(f"Encoder build error: {exc}", file=sys.stderr)
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
