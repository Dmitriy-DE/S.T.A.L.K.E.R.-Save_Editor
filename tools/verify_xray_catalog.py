"""Read-only proof that an installed official X-Ray catalog is addable.

The command validates one real save per original release.  It clones every
official catalog key in memory using the same serializer-family/template
helpers as the writer, rebuilds one temporary container, and parses it again.
No edited save, catalog dump, path, filename, or payload is written or
printed.  Enhanced Edition and community-mod roots are intentionally outside
this verifier until their save format is independently accepted.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.catalog import ItemCatalog  # noqa: E402
from editor.formats import SaveFormat, detect_or_raise  # noqa: E402
from editor.platforms import save_search_paths  # noqa: E402
from editor.releases import official_releases, release_by_id  # noqa: E402
from editor.xray_container import XRayChunk  # noqa: E402
from editor.xray_save import (  # noqa: E402
    XRayFormatSpec,
    _clone_registry_record,
    _definition_serialization_family,
    _object_serialization_family,
    parse_xray,
)
from tools.verify_xray_corpus import _candidate_files  # noqa: E402


def _failure_label(error: BaseException) -> str:
    message = str(error).split("\n", 1)[0].strip()
    if len(message) > 160:
        message = message[:157] + "..."
    return f"{type(error).__name__}: {message}"


def _replace_object_chunk(
    chunks: tuple[XRayChunk, ...], object_data: bytes
) -> bytes:
    """Serialize a new OBJECT chunk without exposing the source bytes."""

    encoded: list[bytes] = []
    replaced = False
    for chunk in chunks:
        payload = object_data if chunk.type == 2 else chunk.data
        if chunk.type == 2:
            if replaced:
                raise ValueError("X-Ray save has more than one OBJECT chunk")
            replaced = True
        encoded.append(struct.pack("<II", chunk.type, len(payload)) + payload)
    if not replaced:
        raise ValueError("X-Ray save has no OBJECT chunk")
    return b"".join(encoded)


def verify_catalog_sample(
    data: bytes,
    spec: XRayFormatSpec,
    catalog: ItemCatalog,
) -> dict[str, Any]:
    """Clone every catalog key and verify the final in-memory parse.

    A catalog family is eligible when the selected save contains at least one
    registry record with that family.  The actual operation then uses the
    exact same ``_clone_registry_record`` path as ``prepare_xray``.  The final
    parse verifies that every appended key is visible as an actor-owned item;
    it does not claim that a game has loaded the result.
    """

    if catalog.release_id != spec.id:
        raise ValueError(
            f"catalog {catalog.release_id!r} does not match format {spec.id!r}"
        )
    parsed = parse_xray(data, spec, with_inventory=True)
    templates: dict[str, Any] = {}
    for obj in parsed.objects:
        if obj.object_id == parsed.actor_id:
            continue
        family = _object_serialization_family(obj, catalog)
        templates.setdefault(family, obj)

    missing_families: Counter[str] = Counter()
    eligible_keys: list[str] = []
    for definition in catalog.items:
        family = _definition_serialization_family(definition)
        if family not in templates:
            missing_families[family] += 1
        else:
            eligible_keys.append(definition.key)

    object_chunk = next(chunk for chunk in parsed.container.chunks if chunk.type == 2)
    object_data = bytearray(object_chunk.data)
    object_count = int.from_bytes(object_data[:4], "little")
    used_ids = {obj.object_id for obj in parsed.objects}
    appended_keys: list[str] = []

    for definition in catalog.items:
        family = _definition_serialization_family(definition)
        prototype = templates.get(family)
        if prototype is None:
            continue
        object_id = max(used_ids, default=0) + 1
        while object_id in used_ids:
            object_id += 1
        used_ids.add(object_id)
        record = _clone_registry_record(
            parsed,
            prototype,
            item_key=definition.key,
            object_id=object_id,
            actor_id=parsed.actor_id,
            family=family,
            quantity=1,
        )
        object_data.extend(record)
        object_count += 1
        appended_keys.append(definition.key)

    object_data[:4] = object_count.to_bytes(4, "little")
    rebuilt_raw = _replace_object_chunk(parsed.container.chunks, bytes(object_data))
    rebuilt = parsed.container.build(rebuilt_raw)
    after = parse_xray(rebuilt, spec, with_inventory=True)

    before_counts = Counter(item.type_key for item in parsed.inventory)
    after_counts = Counter(item.type_key for item in after.inventory)
    roundtrip_added_count = sum(
        1
        for key in appended_keys
        if after_counts[key] >= before_counts[key] + 1
    )
    return {
        "catalog_items": len(catalog.items),
        "full_key_coverage_count": len(eligible_keys),
        "missing_serialization_families": dict(sorted(missing_families.items())),
        "roundtrip_added_count": roundtrip_added_count,
        "final_inventory_count": len(after.inventory),
    }


def _catalog_for(format_: SaveFormat, path: Path) -> ItemCatalog | None:
    loader = getattr(format_, "catalog_for_source", None)
    if not callable(loader):
        return None
    value = loader(str(path))
    return value if isinstance(value, ItemCatalog) else None


def verify_catalogs(
    roots_by_release: Mapping[str, Sequence[Path]] | None = None,
) -> dict[str, Any]:
    """Validate one available save for each original official release."""

    overrides = {
        release_id: tuple(Path(path) for path in paths)
        for release_id, paths in (roots_by_release or {}).items()
    }
    profiles: list[dict[str, Any]] = []
    for release in official_releases():
        if release.edition != "original":
            continue
        roots = overrides.get(release.id)
        if roots is None:
            try:
                roots = save_search_paths(release.id)
            except Exception:
                roots = ()
        files = _candidate_files(release, roots)
        row: dict[str, Any] = {
            "release_id": release.id,
            "candidate_count": len(files),
            "validated_count": 0,
            "failure_summaries": [],
        }
        if files:
            try:
                path = files[0]
                data = path.read_bytes()
                format_ = detect_or_raise(data, display_name=release.id)
                spec = getattr(format_, "spec", None)
                if not isinstance(spec, XRayFormatSpec):
                    raise ValueError("registered format has no X-Ray specification")
                catalog = _catalog_for(format_, path)
                if catalog is None:
                    raise ValueError("official X-Ray catalog is unavailable")
                row.update(verify_catalog_sample(data, spec, catalog))
                row["validated_count"] = 1
            except Exception as error:
                row["failure_summaries"] = [{"error": _failure_label(error), "count": 1}]
        profiles.append(row)
    return {"profiles": profiles}


def _parse_override(value: str) -> tuple[str, Path]:
    release_id, separator, raw_path = value.partition("=")
    if not separator or not release_id.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("ожидалось release_id=PATH")
    try:
        release = release_by_id(release_id.strip())
    except KeyError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    if release.edition != "original":
        raise argparse.ArgumentTypeError("verifier accepts original releases only")
    return release_id.strip(), Path(raw_path).expanduser()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        metavar="RELEASE_ID=PATH",
        type=_parse_override,
        help="override one original release search root; repeatable",
    )
    args = parser.parse_args(argv)
    overrides: dict[str, list[Path]] = {}
    for release_id, path in args.root:
        overrides.setdefault(release_id, []).append(path)
    print(json.dumps(verify_catalogs(overrides), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
