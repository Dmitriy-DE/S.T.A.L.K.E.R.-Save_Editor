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

from editor.equipment_research import (  # noqa: E402
    analyze_equipment_corpus,
    analyze_equipment_samples,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only release-scoped Equipment evidence report"
    )
    parser.add_argument(
        "samples",
        nargs="*",
        type=Path,
        help="explicit save files; no file is modified",
    )
    parser.add_argument(
        "--sample",
        action="append",
        type=Path,
        default=[],
        help="legacy explicit save path; may be repeated",
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        help="explicit corpus root; every input is read-only",
    )
    parser.add_argument(
        "--report",
        "--output",
        dest="report_path",
        type=Path,
        help="write the anonymized corpus report to this path",
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


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.input_root is not None:
            if args.samples or args.sample:
                raise ValueError("--input-root cannot be combined with explicit samples")
            if args.report_path is None:
                raise ValueError("--input-root requires --report or --output")
            corpus = analyze_equipment_corpus(
                args.input_root,
                expected_release_id=args.expected_release_id,
            )
            payload = corpus.as_dict()
            _write_report(args.report_path, payload)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(
                    f"Corpus: {corpus.accepted_count}/{corpus.file_count} accepted; "
                    f"rejected={corpus.rejected_count}; report={args.report_path}"
                )
            return 0
        paths = tuple(args.samples) + tuple(args.sample)
        if not paths:
            raise ValueError("provide explicit samples or --input-root with --report")
        report = analyze_equipment_samples(paths, expected_release_id=args.expected_release_id)
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
