from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.render_capabilities import (
    BEGIN_MARKER,
    END_MARKER,
    render_capability_table,
)

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (ROOT / "README.md", ROOT / "docs" / "STATUS.md")
EXPECTED_COLUMNS = (
    "Release",
    "edit_money",
    "edit_stacks",
    "move_items",
    "add_items",
    "remove_items",
    "edit_durability",
    "edit_upgrades",
    "edit_relations",
    "edit_player_faction",
    "edit_placement",
    "equipment_durability",
    "equipment_upgrades",
    "equipment_placement",
    "equipment_add",
    "equipment_remove",
)


def _generated_block(document: Path) -> str:
    text = document.read_text(encoding="utf-8")
    assert text.count(BEGIN_MARKER) == 1
    assert text.count(END_MARKER) == 1
    start = text.index(BEGIN_MARKER) + len(BEGIN_MARKER)
    end = text.index(END_MARKER)
    return text[start:end].strip()


def _table_cells(line: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in line.strip("|").split("|"))


def test_capability_tables_match_the_format_and_release_registries() -> None:
    expected_rows = {
        "S.T.A.L.K.E.R. 2: Heart of Chornobyl": (
            "experimental",
            "experimental",
            "unsupported",
            "unsupported",
            "unsupported",
            "experimental",
            "unsupported",
            "unsupported",
            "unsupported",
            "unsupported",
            "experimental",
            "research",
            "unsupported",
            "unsupported",
            "unsupported",
        ),
        "S.T.A.L.K.E.R.: Shadow of Chernobyl": (
            "verified",
            "verified",
            "unsupported",
            "verified",
            "verified",
            "experimental",
            "unsupported",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "unsupported",
            "experimental",
            "experimental",
            "experimental",
        ),
        "S.T.A.L.K.E.R.: Clear Sky": (
            "verified",
            "verified",
            "unsupported",
            "verified",
            "verified",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
        ),
        "S.T.A.L.K.E.R.: Call of Pripyat": (
            "verified",
            "verified",
            "unsupported",
            "verified",
            "verified",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
            "experimental",
        ),
        "S.T.A.L.K.E.R.: Shadow of Chornobyl — Enhanced Edition": ("experimental", "experimental", "unsupported", "experimental", "experimental") + ("unsupported",) * 10,
        "S.T.A.L.K.E.R.: Clear Sky — Enhanced Edition": ("experimental", "experimental", "unsupported", "experimental", "experimental") + ("unsupported",) * 10,
        "S.T.A.L.K.E.R.: Call of Pripyat — Enhanced Edition": ("experimental", "experimental", "unsupported", "experimental", "experimental") + ("unsupported",) * 10,
    }
    rendered_table = render_capability_table().splitlines()
    rendered_rows = {
        cells[0]: cells[1:]
        for cells in (_table_cells(line) for line in rendered_table[2:])
    }

    assert _table_cells(rendered_table[0]) == EXPECTED_COLUMNS
    assert rendered_rows == expected_rows


def test_readme_and_status_capability_tables_are_fresh() -> None:
    generated = render_capability_table()

    for document in DOCUMENTS:
        assert _generated_block(document) == generated


def test_capability_generator_cli_check_succeeds_when_documents_are_current() -> None:
    result = subprocess.run(
        [sys.executable, "tools/render_capabilities.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
