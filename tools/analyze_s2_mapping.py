#!/usr/bin/env python3
"""Compare compact S2 inventory keys across saves without modifying them.

The command prints hashes, counts and opaque ``type_key`` observations only.
It never writes an input or output save and never assigns a public prototype
SID to an observed key.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.s2_mapping import analyze_s2_samples  # noqa: E402


def _read_samples(paths: Sequence[Path]) -> dict[str, bytes]:
    samples: dict[str, bytes] = {}
    for index, path in enumerate(paths, 1):
        samples[f"sample-{index}"] = path.read_bytes()
    return samples


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saves", nargs="+", type=Path, help="S2 .sav files to compare")
    args = parser.parse_args(argv)
    report = analyze_s2_samples(_read_samples(args.saves))
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
