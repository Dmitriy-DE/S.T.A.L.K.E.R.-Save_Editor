"""Deterministic, read-only corpus verification for official save profiles.

The verifier deliberately reports aggregate evidence only.  It never prints a
save path, filename, payload, or catalog bytes, and it never writes an edited
save to disk.  Local roots can be supplied as ``release_id=PATH`` pairs for a
repeatable fixture/CI run; without overrides the normal read-only platform
search paths are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

# Make ``python tools/verify_xray_corpus.py`` behave like the other repository
# tools when invoked from any working directory.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.formats import SaveFormat, detect_or_raise  # noqa: E402
from editor.models import EditPlan, SourceRef  # noqa: E402
from editor.platforms import save_search_paths  # noqa: E402
from editor.releases import ReleaseDescriptor, official_releases, release_by_id  # noqa: E402


def _failure_label(error: BaseException) -> str:
    """Keep failure summaries useful without leaking a private path."""

    message = str(error).split("\n", 1)[0].strip()
    if len(message) > 160:
        message = message[:157] + "..."
    return f"{type(error).__name__}: {message}"


def _candidate_files(
    release: ReleaseDescriptor,
    roots: Iterable[Path],
) -> tuple[Path, ...]:
    files: set[Path] = set()
    for raw_root in roots:
        root = Path(raw_root).expanduser()
        try:
            if root.is_file():
                if root.suffix.casefold() in release.extensions:
                    files.add(root.resolve())
                continue
            if not root.is_dir():
                continue
            for path in root.iterdir():
                if path.is_file() and path.suffix.casefold() in release.extensions:
                    files.add(path.resolve())
        except OSError:
            continue
    return tuple(sorted(files, key=lambda path: path.as_posix().casefold()))


def _plan(data: bytes, *, locator: str = "corpus") -> EditPlan:
    return EditPlan(
        source=SourceRef(
            kind="local",
            locator=locator,
            sha256=hashlib.sha256(data).hexdigest(),
        )
    )


def _format_version(info: Any) -> str:
    value = info.format_version
    if value is None:
        value = info.container_version
    return "unknown" if value is None else str(value)


def _catalog_for(format_: SaveFormat, path: Path) -> Any:
    loader = getattr(format_, "catalog_for_source", None)
    if not callable(loader):
        return None
    try:
        return loader(str(path))
    except Exception:
        return None


def _run_edit_roundtrip(
    format_: SaveFormat,
    data: bytes,
    info: Any,
    *,
    catalog: Any = None,
    source_name: str | None = None,
) -> int:
    """Run in-memory money/stack/structural checks and return successes."""

    successes = 0
    source = _plan(data, locator="corpus")
    if format_.capabilities.edit_money and info.money is not None:
        target = 0 if info.money > 0 else 1
        plan = EditPlan(source=source.source, money=target)
        prepared = format_.prepare(
            data,
            plan,
            source_name=source_name,
            catalog=catalog,
        )
        after = format_.inspect(prepared.data)
        if after.money != target:
            raise RuntimeError("money round-trip value mismatch")
        successes += 1

    if format_.capabilities.edit_stacks:
        item = next(
            (
                value
                for value in info.inventory
                if value.editable_count and value.count is not None
            ),
            None,
        )
        if item is not None:
            target = item.count + 1 if item.count < item.count_max else item.count - 1
            if target >= 1 and target != item.count:
                plan = EditPlan(source=source.source, stacks=((item.handle, target),))
                prepared = format_.prepare(
                    data,
                    plan,
                    source_name=source_name,
                    catalog=catalog,
                )
                after = format_.inspect(prepared.data)
                checked = next(
                    (value for value in after.inventory if value.handle == item.handle),
                    None,
                )
                if checked is None or checked.count != target:
                    raise RuntimeError("stack round-trip value mismatch")
                successes += 1
    return successes


def verify_corpus(
    roots_by_release: Mapping[str, Sequence[Path]] | None = None,
) -> dict[str, Any]:
    """Verify every supplied/auto-discovered official release corpus."""

    overrides = {
        release_id: tuple(Path(path) for path in paths)
        for release_id, paths in (roots_by_release or {}).items()
    }
    summaries: list[dict[str, Any]] = []
    catalog_cache: dict[str, Any] = {}
    for release in official_releases():
        roots = overrides.get(release.id)
        if roots is None:
            try:
                roots = save_search_paths(release.id)
            except Exception:
                roots = ()
        files = _candidate_files(release, roots)
        versions: Counter[str] = Counter()
        failures: Counter[str] = Counter()
        parsed = 0
        sha_matches = 0
        edit_roundtrips = 0
        for path in files:
            try:
                data = path.read_bytes()
                format_ = detect_or_raise(data, display_name=release.id)
                info = format_.inspect(data, with_inventory=True)
                versions[_format_version(info)] += 1
                parsed += 1
                if format_.id not in catalog_cache:
                    catalog_cache[format_.id] = _catalog_for(format_, path)
                cached_catalog = catalog_cache[format_.id]
                catalog = cached_catalog
                no_op = format_.prepare(
                    data,
                    _plan(data),
                    source_name=str(path) if catalog is not None else None,
                    catalog=catalog,
                )
                if no_op.data == data and no_op.output_sha256 == hashlib.sha256(data).hexdigest():
                    sha_matches += 1
                edit_roundtrips += _run_edit_roundtrip(
                    format_,
                    data,
                    info,
                    catalog=catalog,
                    source_name=str(path),
                )
            except Exception as error:
                failures[_failure_label(error)] += 1
        summaries.append(
            {
                "release_id": release.id,
                "candidate_count": len(files),
                "parsed_count": parsed,
                "versions": dict(sorted(versions.items())),
                "sha_match_count": sha_matches,
                "edit_roundtrip_count": edit_roundtrips,
                "failure_summaries": [
                    {"error": label, "count": count}
                    for label, count in sorted(failures.items())
                ],
            }
        )
    return {"profiles": summaries}


def _parse_override(value: str) -> tuple[str, Path]:
    release_id, separator, raw_path = value.partition("=")
    if not separator or not release_id.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("ожидалось release_id=PATH")
    try:
        release_by_id(release_id.strip())
    except KeyError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return release_id.strip(), Path(raw_path).expanduser()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="RELEASE_ID=PATH",
        type=_parse_override,
        help="override one release search root; repeatable",
    )
    args = parser.parse_args(argv)
    overrides: dict[str, list[Path]] = {}
    for release_id, path in args.root:
        overrides.setdefault(release_id, []).append(path)
    print(json.dumps(verify_corpus(overrides), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
