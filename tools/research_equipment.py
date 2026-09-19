#!/usr/bin/env python3
"""Read-only equipment evidence reporter for explicit save samples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.equipment_research import analyze_equipment_samples  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only release-scoped Equipment evidence report"
    )
    parser.add_argument(
        "samples",
        nargs="+",
        type=Path,
        help="explicit save files; no file is modified",
    )
    parser.add_argument(
        "--release",
        dest="expected_release_id",
        help="reject samples that do not belong to this release id",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the complete machine-readable report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        report = analyze_equipment_samples(
            tuple(args.samples),
            expected_release_id=args.expected_release_id,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return 0
    print(f"Release: {report.release_id}")
    print(f"Durability maturity: {report.maturity}")
    print(f"Samples: {len(report.samples)}")
    for sample in report.samples:
        categories = ", ".join(
            f"{category}={count}" for category, count in sample.category_counts
        ) or "none"
        print(f"- {sample.path}: {sample.sha256} ({categories})")
    for blocker in report.blockers:
        print(f"Blocker: {blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
