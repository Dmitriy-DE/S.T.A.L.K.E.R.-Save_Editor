#!/usr/bin/env python3
"""Report S.T.A.L.K.E.R. 2 name/icon coverage for a list of SIDs.

    python tools/s2_coverage.py [--sids data/s2_sid_sample.json] [--gaps gaps.json]

``--gaps`` writes the SIDs that still lack an English name or an icon, the
input for filling them (docs/roadmap KB-4).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from editor.s2_items import s2_entry  # noqa: E402


def coverage(sids: dict[str, str]) -> tuple[dict[str, Counter], list[dict]]:
    stats: dict[str, Counter] = {}
    gaps = []
    for sid, kind in sorted(sids.items()):
        entry = s2_entry(sid) or {}
        names = entry.get("names") or {}
        row = stats.setdefault(kind, Counter())
        row["total"] += 1
        row["ru"] += "ru" in names
        row["en"] += "en" in names
        row["icon"] += bool(entry.get("icon"))
        if "en" not in names or not entry.get("icon"):
            gaps.append({"sid": sid, "kind": kind, "ru_official": names.get("ru"), "en": names.get("en")})
    return stats, gaps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sids", type=Path, default=ROOT / "data" / "s2_sid_sample.json")
    parser.add_argument("--gaps", type=Path)
    args = parser.parse_args(argv)
    stats, gaps = coverage(json.loads(args.sids.read_text(encoding="utf-8"))["sids"])
    for kind, row in stats.items():
        print(f"{kind:8} total {row['total']:4}  ru {row['ru']:4}  en {row['en']:4}  icon {row['icon']:4}")
    if args.gaps:
        args.gaps.write_text(json.dumps(gaps, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
