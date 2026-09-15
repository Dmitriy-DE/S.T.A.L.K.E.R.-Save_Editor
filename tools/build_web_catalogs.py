"""Generate the compact, metadata-only browser item catalog.

The input roots are explicit official installation resource roots.  The output
contains serialized item keys and the already-proven serializer metadata only;
it never copies config files, localization text, prototypes, or save bytes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

# Make direct invocations behave like the other repository tools.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.releases import release_by_id  # noqa: E402
from editor.xray_catalog import XRayCatalogProvider  # noqa: E402


def _parse_root(value: str) -> tuple[str, Path]:
    release_id, separator, raw_path = value.partition("=")
    if not separator or not release_id.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("ожидалось release_id=PATH")
    try:
        release_by_id(release_id.strip())
    except KeyError as error:
        raise argparse.ArgumentTypeError(str(error)) from error
    return release_id.strip(), Path(raw_path).expanduser()


def build_catalogs(roots: Sequence[tuple[str, Path]]) -> dict[str, object]:
    provider = XRayCatalogProvider()
    releases: dict[str, object] = {}
    for release_id, root in roots:
        release = release_by_id(release_id)
        catalog = provider.load(release, root)
        if catalog is None:
            raise ValueError(f"official catalog unavailable for {release_id}")
        releases[release_id] = {
            "source": "official-resource-metadata",
            "items": [
                {
                    "key": item.key,
                    "category": item.category,
                    "max_stack": item.max_stack,
                    "serialization_family": item.serialization_family,
                }
                for item in sorted(catalog.items, key=lambda value: value.key.casefold())
            ],
        }
    return {"schema_version": 1, "releases": releases}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", default=[], type=_parse_root)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    rendered = json.dumps(
        build_catalogs(args.root),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
