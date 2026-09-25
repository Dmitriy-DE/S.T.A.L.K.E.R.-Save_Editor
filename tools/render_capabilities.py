#!/usr/bin/env python3
"""Render the official release capability matrix into README and STATUS."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from editor.releases import EquipmentFeature

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BEGIN_MARKER = "<!-- BEGIN CAPABILITIES -->"
END_MARKER = "<!-- END CAPABILITIES -->"
DOCUMENTS = (ROOT / "docs" / "STATUS.md", ROOT / "README.md")

FORMAT_OPERATIONS = (
    ("edit_money", "edit_money"),
    ("edit_stacks", "edit_stacks"),
    ("move_items", "move_items"),
    ("add_items", "add_items"),
    ("remove_items", "remove_items"),
    ("edit_durability", "edit_durability"),
    ("edit_upgrades", "edit_upgrades"),
    ("edit_relations", "edit_relations"),
    ("edit_player_faction", "edit_player_faction"),
    ("edit_placement", "edit_placement"),
)
EQUIPMENT_OPERATIONS: tuple[tuple[EquipmentFeature, str], ...] = (
    ("durability", "equipment_durability"),
    ("upgrades", "equipment_upgrades"),
    ("placement", "equipment_placement"),
    ("add", "equipment_add"),
    ("remove", "equipment_remove"),
)
UNSUPPORTED = "unsupported"


def render_capability_table() -> str:
    """Return release mutation maturities directly from the shared registries."""

    from editor.formats import formats
    from editor.releases import official_releases

    registered_formats = {format_.release_id: format_ for format_ in formats()}
    columns = (
        "Release",
        *(column for _, column in FORMAT_OPERATIONS),
        *(column for _, column in EQUIPMENT_OPERATIONS),
    )
    rows = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]

    for release in official_releases():
        format_ = registered_formats.get(release.id)
        format_values = tuple(
            format_.capabilities.support(field).maturity
            if format_ is not None
            else UNSUPPORTED
            for field, _ in FORMAT_OPERATIONS
        )
        equipment_values = tuple(
            release.equipment.support(feature).maturity
            if release.equipment is not None
            else UNSUPPORTED
            for feature, _ in EQUIPMENT_OPERATIONS
        )
        rows.append(
            "| "
            + " | ".join((release.title, *format_values, *equipment_values))
            + " |"
        )

    return "\n".join(rows)


def _replace_marked_section(document: Path, generated: str) -> str:
    text = document.read_text(encoding="utf-8")
    if text.count(BEGIN_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise ValueError(
            f"{document.relative_to(ROOT)} must contain exactly one capability marker pair"
        )
    start = text.index(BEGIN_MARKER) + len(BEGIN_MARKER)
    end = text.index(END_MARKER)
    if end < start:
        raise ValueError(f"{document.relative_to(ROOT)} capability markers are reversed")
    return f"{text[:start]}\n{generated}\n{text[end:]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if README or STATUS is stale"
    )
    args = parser.parse_args(argv)

    generated = render_capability_table()
    rendered_documents = {
        document: _replace_marked_section(document, generated)
        for document in DOCUMENTS
    }

    if args.check:
        stale = [
            document
            for document, rendered in rendered_documents.items()
            if rendered != document.read_text(encoding="utf-8")
        ]
        for document in stale:
            print(
                f"{document.relative_to(ROOT)} capability table is stale; "
                "run python tools/render_capabilities.py",
                file=sys.stderr,
            )
        return int(bool(stale))

    for document, rendered in rendered_documents.items():
        if rendered != document.read_text(encoding="utf-8"):
            document.write_text(rendered, encoding="utf-8")
            print(f"updated {document.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
