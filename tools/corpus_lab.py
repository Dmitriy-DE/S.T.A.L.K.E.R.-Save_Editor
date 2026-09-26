#!/usr/bin/env python3
"""Analyze local save corpora without putting paths or names in the report."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
_KNOWN_XRAY_CHUNKS = frozenset({0, 1, 2, 5, 9})

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.catalog import GameCatalog, ItemCatalog  # noqa: E402
from editor.formats import SaveFormat, detect_or_raise  # noqa: E402
from editor.item_names import catalog_definition, item_label  # noqa: E402
from editor.models import EditPlan, PreparedEdit, SourceRef  # noqa: E402
from editor.official_names import official_name  # noqa: E402
from editor.platforms import installed_releases  # noqa: E402
from editor.prepare import prepare_edit  # noqa: E402
from editor.releases import official_releases  # noqa: E402
from editor.service import EditorService  # noqa: E402
from editor.xray_catalog import has_mod_overlay  # noqa: E402
from editor.xray_container import XRayContainer  # noqa: E402
from editor.xray_save import prepare_xray  # noqa: E402
from save_format import InventoryItem, SaveInfo, decompress_save, rebuild_compact  # noqa: E402

MutationStatus = Literal["passed", "failed", "skipped"]
ParseStatus = Literal["ok", "error"]
SAVE_EXTENSIONS = frozenset(
    extension
    for release in official_releases()
    for extension in release.extensions
    if extension not in {".dds", ".info"}
)


@dataclass(frozen=True)
class MutationResult:
    status: MutationStatus
    delta: int | None = None
    reason: str | None = None
    error_type: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"status": self.status}
        if self.delta is not None:
            payload["delta"] = self.delta
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.error_type is not None:
            payload["error_type"] = self.error_type
        return payload


@dataclass(frozen=True)
class CorpusSample:
    sha256: str | None
    release: str
    format: str
    parse_status: ParseStatus
    error_type: str | None = None
    item_count: int | None = None
    names_covered: int | None = None
    icons_covered: int | None = None
    available_operations: tuple[str, ...] = ()
    operation_levels: tuple[tuple[str, str], ...] = ()
    no_op_round_trip: MutationStatus | None = None
    test_mutations: tuple[tuple[str, MutationResult], ...] = ()
    modded: bool | None = None
    modded_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "release": self.release,
            "format": self.format,
            "parse_status": self.parse_status,
            "error_type": self.error_type,
            "item_count": self.item_count,
            "name_coverage": (
                None
                if self.item_count is None or self.names_covered is None
                else {"covered": self.names_covered, "total": self.item_count}
            ),
            "icon_coverage": (
                None
                if self.item_count is None or self.icons_covered is None
                else {"covered": self.icons_covered, "total": self.item_count}
            ),
            "available_operations": list(self.available_operations),
            "operation_levels": dict(self.operation_levels),
            "no_op_round_trip": self.no_op_round_trip,
            "test_mutations": {
                name: result.as_dict() for name, result in self.test_mutations
            },
            "modded": self.modded,
            "modded_reasons": list(self.modded_reasons),
        }


@dataclass(frozen=True)
class CorpusReport:
    files_seen: int
    parsed_count: int
    parse_error_count: int
    no_op_pass_count: int
    no_op_fail_count: int
    mutation_pass_count: int
    modded_count: int
    samples: tuple[CorpusSample, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "files_seen": self.files_seen,
            "parsed_count": self.parsed_count,
            "parse_error_count": self.parse_error_count,
            "no_op_pass_count": self.no_op_pass_count,
            "no_op_fail_count": self.no_op_fail_count,
            "mutation_pass_count": self.mutation_pass_count,
            "modded_count": self.modded_count,
            "samples": [sample.as_dict() for sample in self.samples],
        }


@dataclass(frozen=True)
class _InputSnapshot:
    path: Path
    data: bytes
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class _Catalogs:
    items: ItemCatalog | None
    game: GameCatalog | None
    display: ItemCatalog | None


class InputChangedError(ValueError):
    """An input changed while the corpus lab was reading it."""


def default_output_directory() -> Path:
    return Path.home() / ".local" / "share" / "Stalker2SaveEditor" / "corpus-lab"


def _snapshot(path: Path) -> _InputSnapshot:
    try:
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise OSError(type(exc).__name__) from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(data) != after.st_size
    ):
        raise InputChangedError("input changed during analysis")
    return _InputSnapshot(path, data, after.st_size, after.st_mtime_ns)


def _assert_unchanged(snapshot: _InputSnapshot) -> None:
    try:
        current_stat = snapshot.path.stat()
        current = snapshot.path.read_bytes()
    except OSError as exc:
        raise InputChangedError("input changed during analysis") from exc
    if (
        current_stat.st_size != snapshot.size
        or current_stat.st_mtime_ns != snapshot.mtime_ns
        or current != snapshot.data
    ):
        raise InputChangedError("input changed during analysis")


def _candidate_files(roots: Sequence[Path]) -> tuple[Path, ...]:
    candidates: dict[Path, None] = {}
    for root in roots:
        try:
            paths = root.rglob("*")
            for path in paths:
                if (
                    not path.is_symlink()
                    and path.is_file()
                    and path.suffix.casefold() in SAVE_EXTENSIONS
                ):
                    candidates[path.resolve()] = None
        except OSError as exc:
            raise ValueError("unable to enumerate corpus root") from exc
    return tuple(sorted(candidates, key=lambda path: path.as_posix().casefold()))


def _official_roots() -> dict[str, tuple[Path, ...]]:
    roots: dict[str, list[Path]] = {}
    try:
        games = installed_releases()
    except Exception:
        return {}
    for game in games:
        try:
            roots.setdefault(game.release_id, []).append(Path(game.install_dir).resolve())
        except OSError:
            continue
    return {release: tuple(values) for release, values in roots.items()}


def _catalogs_for(format_: SaveFormat, path: Path) -> _Catalogs:
    source_name = str(path)
    item_loader = getattr(format_, "catalog_for_source", None)
    game_loader = getattr(format_, "game_catalog_for_source", None)
    display_loader = getattr(format_, "display_catalog_for_source", None)
    items = item_loader(source_name) if callable(item_loader) else None
    game = game_loader(source_name) if callable(game_loader) else None
    display = display_loader(source_name) if callable(display_loader) else None
    return _Catalogs(items, game, display)


def _coverage(
    info: SaveInfo,
    release_id: str,
    catalogs: _Catalogs,
) -> tuple[int, int, int]:
    inventory = info.inventory
    catalog = catalogs.display or catalogs.items
    if catalog is None and catalogs.game is not None:
        catalog = catalogs.game.items
    named = 0
    icons = 0
    for item in inventory:
        definition = catalog_definition(catalog, item)
        official = official_name(release_id, "items", item.type_key)
        label = item_label(item, catalog, release_id=release_id)
        raw_labels = {
            str(value).strip().casefold()
            for value in (item.type_key, item.display_name)
            if value
        }
        if (
            bool(official)
            or (definition is not None and bool(definition.display_name))
            or (label is not None and bool(label) and label.strip().casefold() not in raw_labels)
        ):
            named += 1
        if definition is None or not definition.icon_texture:
            continue
        if release_id == "stalker2" or (
            definition.icon_x is not None and definition.icon_y is not None
        ):
            icons += 1
    return len(inventory), named, icons


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _modded_reasons(
    data: bytes,
    format_: SaveFormat,
    info: SaveInfo,
    catalogs: _Catalogs,
    official_roots: dict[str, tuple[Path, ...]],
    path: Path,
) -> tuple[str, ...]:
    reasons: set[str] = set()
    if getattr(info, "unresolved_handles", ()):
        reasons.add("unknown_sections")
    warnings = tuple(str(warning).casefold() for warning in getattr(info, "warnings", ()))
    if any("unknown" in warning or "неизвестн" in warning for warning in warnings):
        reasons.add("unknown_sections")
    if format_.id != "stalker2":
        try:
            chunks = XRayContainer.from_bytes(data).chunk_types
        except Exception:
            chunks = ()
        if any(chunk not in _KNOWN_XRAY_CHUNKS for chunk in chunks):
            reasons.add("unknown_sections")
        current = path.parent
        for root in (current, *current.parents):
            try:
                if has_mod_overlay(root):
                    reasons.add("foreign_catalog")
                    break
            except OSError:
                continue
    if catalogs.display is not None:
        reasons.add("foreign_catalog")
    candidates = [catalogs.items]
    if catalogs.game is not None:
        candidates.append(catalogs.game.items)
    for catalog in candidates:
        if catalog is None or catalog.source_root is None:
            continue
        source_root = Path(catalog.source_root)
        if _is_within(source_root, ROOT):
            continue
        installed = official_roots.get(format_.release_id, ())
        if any(_is_within(source_root, root) for root in installed):
            continue
        reasons.add("foreign_catalog")
    return tuple(sorted(reasons))


def _operation_report(format_: SaveFormat) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    levels = tuple(
        sorted(
            (name, support.maturity)
            for name, support in format_.capabilities.mutation_support.items()
        )
    )
    available = tuple(name for name, maturity in levels if maturity in {"experimental", "verified"})
    return available, levels


def _source_ref(data: bytes) -> SourceRef:
    return SourceRef(
        kind="local",
        locator="corpus-lab-copy",
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _no_op_round_trip(
    data: bytes,
    format_: SaveFormat,
    service: EditorService,
) -> MutationStatus:
    plan = EditPlan(source=_source_ref(data))
    try:
        if format_.id == "stalker2":
            # patch_save intentionally rejects an empty edit plan; use the
            # format's lossless compact rebuild for this no-op check.
            raw = decompress_save(data)
            rebuilt, _decision = rebuild_compact(data, raw, original_raw=raw)
        else:
            rebuilt = service.prepare(data, plan).data
        format_.inspect(rebuilt, with_inventory=True)
    except Exception:
        return "failed"
    return "passed" if rebuilt == data else "failed"


def _prepare_test_copy(
    format_: SaveFormat,
    data: bytes,
    plan: EditPlan,
) -> PreparedEdit:
    """Run an existing format writer against in-memory bytes only."""

    if format_.id == "stalker2":
        return prepare_edit(data, plan)
    spec = getattr(format_, "spec", None)
    if spec is None:
        raise ValueError("format does not expose a copy-test writer")
    return prepare_xray(data, plan, spec)


def _test_money_copy(
    format_: SaveFormat,
    data: bytes,
    money: int | None,
) -> MutationResult:
    if money is None or money >= 2_000_000_000:
        return MutationResult("skipped", reason="money_plus_one_unavailable")
    plan = EditPlan(source=_source_ref(data), money=money + 1)
    try:
        prepared = _prepare_test_copy(format_, data, plan)
        reparsed = format_.inspect(prepared.data)
    except Exception as exc:
        return MutationResult("failed", delta=1, error_type=type(exc).__name__)
    if reparsed.money != money + 1:
        return MutationResult("failed", delta=1, reason="round_trip_mismatch")
    return MutationResult("passed", delta=1)


def _stack_candidate(info: SaveInfo) -> tuple[InventoryItem | None, int | None]:
    candidates = tuple(
        item
        for item in info.inventory
        if item.editable_count and item.count is not None and item.count > 0
    )
    if not candidates:
        return None, None
    item = min(candidates, key=lambda value: value.handle)
    count = item.count
    if count is None:
        return None, None
    if count < item.count_max:
        return item, 1
    if count > 1:
        return item, -1
    return None, None


def _test_stack_copy(format_: SaveFormat, data: bytes, info: SaveInfo) -> MutationResult:
    item, delta = _stack_candidate(info)
    if item is None or delta is None or item.count is None:
        return MutationResult("skipped", reason="editable_stack_unavailable")
    new_count = item.count + delta
    plan = EditPlan(source=_source_ref(data), stacks=((item.handle, new_count),))
    try:
        prepared = _prepare_test_copy(format_, data, plan)
        reparsed = format_.inspect(prepared.data)
    except Exception as exc:
        return MutationResult("failed", delta=delta, error_type=type(exc).__name__)
    after = next(
        (candidate for candidate in reparsed.inventory if candidate.handle == item.handle),
        None,
    )
    if after is None or after.count != new_count:
        return MutationResult("failed", delta=delta, reason="round_trip_mismatch")
    return MutationResult("passed", delta=delta)


def _failed_sample(snapshot: _InputSnapshot | None, exc: BaseException) -> CorpusSample:
    digest = hashlib.sha256(snapshot.data).hexdigest() if snapshot is not None else None
    return CorpusSample(
        sha256=digest,
        release="unknown",
        format="unknown",
        parse_status="error",
        error_type=type(exc).__name__,
    )


def _analyze_one(
    snapshot: _InputSnapshot,
    *,
    service: EditorService,
    official_roots: dict[str, tuple[Path, ...]],
    catalog_cache: dict[tuple[str, Path], _Catalogs],
) -> CorpusSample:
    format_ = detect_or_raise(snapshot.data, display_name="corpus input")
    info = format_.inspect(snapshot.data, with_inventory=True)
    cache_key = (format_.id, snapshot.path.parent)
    catalogs = catalog_cache.get(cache_key)
    if catalogs is None:
        try:
            catalogs = _catalogs_for(format_, snapshot.path)
        except Exception:
            catalogs = _Catalogs(None, None, None)
        catalog_cache[cache_key] = catalogs
    item_count, names_covered, icons_covered = _coverage(info, format_.release_id, catalogs)
    no_op = _no_op_round_trip(snapshot.data, format_, service)
    mutations = (
        ("money_plus_one", _test_money_copy(format_, snapshot.data, info.money)),
        ("stack_delta", _test_stack_copy(format_, snapshot.data, info)),
    )
    available, levels = _operation_report(format_)
    modded_reasons = _modded_reasons(
        snapshot.data,
        format_,
        info,
        catalogs,
        official_roots,
        snapshot.path,
    )
    return CorpusSample(
        sha256=hashlib.sha256(snapshot.data).hexdigest(),
        release=format_.release_id,
        format=format_.id,
        parse_status="ok",
        item_count=item_count,
        names_covered=names_covered,
        icons_covered=icons_covered,
        available_operations=available,
        operation_levels=levels,
        no_op_round_trip=no_op,
        test_mutations=mutations,
        modded=bool(modded_reasons),
        modded_reasons=modded_reasons,
    )


def _validated_roots(roots: Iterable[Path]) -> tuple[Path, ...]:
    normalized: set[Path] = set()
    for raw_root in roots:
        root = Path(raw_root).expanduser()
        try:
            root = root.resolve(strict=True)
        except OSError as exc:
            raise ValueError("each corpus root must exist and be readable") from exc
        if not root.is_dir():
            raise ValueError("each corpus root must be a directory")
        normalized.add(root)
    if not normalized:
        raise ValueError("provide at least one corpus root")
    return tuple(sorted(normalized, key=lambda path: path.as_posix().casefold()))


def _overlaps(left: Path, right: Path) -> bool:
    return _is_within(left, right) or _is_within(right, left)


def _validate_output(output: Path, roots: Sequence[Path]) -> Path:
    resolved = Path(output).expanduser().resolve()
    if any(_overlaps(resolved, root) for root in roots):
        raise ValueError("output directory overlaps an input root")
    return resolved


def analyze_roots(roots: Sequence[Path]) -> CorpusReport:
    normalized = _validated_roots(roots)
    paths = _candidate_files(normalized)
    service = EditorService()
    official = _official_roots()
    catalogs: dict[tuple[str, Path], _Catalogs] = {}
    samples: list[CorpusSample] = []
    for path in paths:
        try:
            snapshot = _snapshot(path)
        except OSError as exc:
            samples.append(_failed_sample(None, exc))
            continue
        try:
            sample = _analyze_one(
                snapshot,
                service=service,
                official_roots=official,
                catalog_cache=catalogs,
            )
        except InputChangedError:
            raise
        except Exception as exc:
            sample = _failed_sample(snapshot, exc)
        finally:
            _assert_unchanged(snapshot)
        samples.append(sample)

    parsed = sum(sample.parse_status == "ok" for sample in samples)
    no_op_pass = sum(sample.no_op_round_trip == "passed" for sample in samples)
    no_op_fail = sum(sample.no_op_round_trip == "failed" for sample in samples)
    mutation_passes = sum(
        mutation.status == "passed"
        for sample in samples
        for _name, mutation in sample.test_mutations
    )
    modded_count = sum(sample.modded is True for sample in samples)
    return CorpusReport(
        files_seen=len(paths),
        parsed_count=parsed,
        parse_error_count=len(samples) - parsed,
        no_op_pass_count=no_op_pass,
        no_op_fail_count=no_op_fail,
        mutation_pass_count=mutation_passes,
        modded_count=modded_count,
        samples=tuple(samples),
    )


def _markdown(report: CorpusReport) -> str:
    rows = [
        "# Save corpus report",
        "",
        f"- Files: {report.files_seen}",
        f"- Parsed: {report.parsed_count}",
        f"- Parse errors: {report.parse_error_count}",
        f"- No-op passed / failed: {report.no_op_pass_count} / {report.no_op_fail_count}",
        f"- Test mutations passed: {report.mutation_pass_count}",
        f"- Modded: {report.modded_count}",
        "",
        "| SHA-256 | Release | Format | Parse | Items | Names | Icons | Operations | No-op | Money +1 | Stack Δ | Modded |",
        "|---|---|---|---|---:|---:|---:|---|---|---|---|---|",
    ]
    for sample in report.samples:
        mutation_map = dict(sample.test_mutations)
        names = (
            "—"
            if sample.item_count is None or sample.names_covered is None
            else f"{sample.names_covered}/{sample.item_count}"
        )
        icons = (
            "—"
            if sample.item_count is None or sample.icons_covered is None
            else f"{sample.icons_covered}/{sample.item_count}"
        )
        operations = ", ".join(sample.available_operations) or "—"
        money = mutation_map.get("money_plus_one")
        stack = mutation_map.get("stack_delta")
        stack_label: str = "—" if stack is None else stack.status
        if stack is not None and stack.delta is not None:
            stack_label = f"{stack.status} ({stack.delta:+d})"
        rows.append(
            "| {sha} | {release} | {format} | {parse} | {items} | {names} | {icons} | {ops} | {noop} | {money} | {stack} | {modded} |".format(
                sha=sample.sha256 or "—",
                release=sample.release,
                format=sample.format,
                parse=sample.parse_status,
                items="—" if sample.item_count is None else sample.item_count,
                names=names,
                icons=icons,
                ops=operations,
                noop=sample.no_op_round_trip or "—",
                money="—" if money is None else money.status,
                stack=stack_label,
                modded="—" if sample.modded is None else str(sample.modded).lower(),
            )
        )
    return "\n".join(rows) + "\n"


def _write_file(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def write_report(output: Path, report: CorpusReport) -> None:
    output.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    _write_file(output / "report.json", payload)
    _write_file(output / "report.md", _markdown(report))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", nargs="+", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=default_output_directory())
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        roots = _validated_roots(args.roots)
        output = _validate_output(args.out, roots)
        report = analyze_roots(roots)
        write_report(output, report)
    except (OSError, ValueError) as exc:
        reason = "input changed during analysis" if isinstance(exc, InputChangedError) else str(exc)
        print(f"Error: {reason}", file=sys.stderr)
        return 2
    print(
        f"Corpus Lab: files={report.files_seen} parsed={report.parsed_count} "
        f"errors={report.parse_error_count} modded={report.modded_count}; reports written"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
