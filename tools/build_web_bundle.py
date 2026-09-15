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
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "web" / "pysrc.json"

# Only what the browser actually needs: parse a save, build an immutable edit
# plan and apply it.  Storage, cloud transactions and platform paths stay out -
# a browser tab has no backup directory, no Steam helper and no user data dir.
MODULES = (
    "save_format.py",
    "editor/__init__.py",
    "editor/capabilities.py",
    "editor/catalog.py",
    "editor/codec.py",
    "editor/formats.py",
    "editor/models.py",
    "editor/prepare.py",
    "editor/releases.py",
    "editor/xray_container.py",
    "editor/xray_catalog.py",
    "editor/xray_save.py",
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
        return 0

    BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    if not BUNDLE.is_file() or BUNDLE.read_text(encoding="utf-8") != rendered:
        BUNDLE.write_text(rendered, encoding="utf-8")
        print(f"updated {BUNDLE.relative_to(ROOT)} ({bundle['source_sha256'][:12]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
