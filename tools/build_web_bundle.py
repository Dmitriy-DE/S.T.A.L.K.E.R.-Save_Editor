#!/usr/bin/env python3
"""Bundle the Python core for the browser build.

The browser runs the same parser as the desktop app.  To keep that true rather
than aspirational, the sources are copied into one generated JSON file by this
script instead of being maintained as a second copy, and `--check` fails when
the bundle no longer matches the repository.

    python3 tools/build_web_bundle.py           # regenerate web/pysrc.json
    python3 tools/build_web_bundle.py --check   # fail if it is stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "web" / "pysrc.json"
STATIC_ASSETS = (
    ("assets/fonts/Oswald[wght].ttf", "web/assets/fonts/Oswald[wght].ttf"),
    ("assets/fonts/Oswald-OFL.txt", "web/assets/fonts/Oswald-OFL.txt"),
    *(
        (f"assets/ui/shell_icons/{name}.svg", f"web/assets/ui/shell_icons/{name}.svg")
        for name in ("sound-on", "sound-off", "motion-on", "motion-off")
    ),
    # Interface translations shared with the desktop app (see editor/i18n.py).
    *(
        (f"locales/{path.name}", f"web/locales/{path.name}")
        for path in sorted((ROOT / "locales").glob("*.json"))
        if not path.name.startswith("_")
    ),
)

# Only what the browser actually needs: parse a save, build an immutable edit
# plan and apply it.  Storage, cloud transactions and platform paths stay out -
# a browser tab has no backup directory, native Steam access or user data dir.
MODULES = (
    "save_format.py",
    "editor/__init__.py",
    "editor/capabilities.py",
    "editor/capability_types.py",
    "editor/catalog.py",
    "editor/catalog_bundle.py",
    "editor/codec.py",
    "editor/equipment.py",
    "editor/equipment_matrix.py",
    "editor/formats.py",
    "editor/i18n.py",
    "editor/item_names.py",
    "editor/official_names.py",
    "editor/s2_items.py",
    "editor/kraken_blocks.py",
    "editor/models.py",
    "editor/prepare.py",
    "editor/releases.py",
    "editor/s2_catalog.py",
    "editor/s2_item_state.py",
    "editor/s2_names.py",
    "editor/xray_container.py",
    "editor/xray_factions.py",
    "editor/xray_catalog.py",
    "editor/xray_delete.py",
    "editor/xray_save.py",
    "editor/xray_slots.py",
    "editor/xray_item_state.py",
    "editor/xray_relations.py",
)


def build() -> dict[str, Any]:
    files = {name: (ROOT / name).read_text(encoding="utf-8") for name in MODULES}
    digest = hashlib.sha256()
    for name in MODULES:
        digest.update(name.encode("utf-8"))
        digest.update(files[name].encode("utf-8"))
    return {
        "version": 1,
        "source_sha256": digest.hexdigest(),
        "files": files,
    }


INDEX = ROOT / "web" / "index.html"
_VERSION_BADGE = re.compile(r'(<span class="badge badge-version">)v[^<]*(</span>)')


def _versioned_index() -> str:
    """Stamp the shipped VERSION into the page header badge."""

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    html = INDEX.read_text(encoding="utf-8")
    return _VERSION_BADGE.sub(lambda match: f"{match.group(1)}v{version}{match.group(2)}", html, count=1)


def static_assets_current() -> bool:
    return all(
        (ROOT / target).is_file()
        and (ROOT / source).read_bytes() == (ROOT / target).read_bytes()
        for source, target in STATIC_ASSETS
    )


def write_static_assets() -> None:
    for source, target in STATIC_ASSETS:
        destination = ROOT / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = (ROOT / source).read_bytes()
        if not destination.is_file() or destination.read_bytes() != payload:
            destination.write_bytes(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the bundle is current")
    args = parser.parse_args(argv)

    bundle = build()
    rendered = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not BUNDLE.is_file() or BUNDLE.read_text(encoding="utf-8") != rendered:
            print(
                "web/pysrc.json is out of date; run python3 tools/build_web_bundle.py",
                file=sys.stderr,
            )
            return 1
        if INDEX.read_text(encoding="utf-8") != _versioned_index():
            print(
                "web/index.html version badge is stale; run python3 tools/build_web_bundle.py",
                file=sys.stderr,
            )
            return 1
        if not static_assets_current():
            print(
                "web display font assets are out of date; run python3 tools/build_web_bundle.py",
                file=sys.stderr,
            )
            return 1
        return 0

    BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    if not BUNDLE.is_file() or BUNDLE.read_text(encoding="utf-8") != rendered:
        BUNDLE.write_text(rendered, encoding="utf-8")
        print(f"updated {BUNDLE.relative_to(ROOT)} ({bundle['source_sha256'][:12]}…)")
    write_static_assets()
    stamped = _versioned_index()
    if INDEX.read_text(encoding="utf-8") != stamped:
        INDEX.write_text(stamped, encoding="utf-8")
        print(f"updated {INDEX.relative_to(ROOT)} version badge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
