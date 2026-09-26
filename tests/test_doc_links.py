"""Verify that all markdown documentation links and anchors are valid."""

from __future__ import annotations

from pathlib import Path
import tempfile

import tools.check_doc_links as checker


def test_no_broken_doc_links() -> None:
    """All relative markdown links and anchors in README.md and docs/ must exist."""
    broken = checker.find_broken_links()
    failures = [
        f"{item.file}:{item.line}: [{item.text}]({item.target}) -> {item.reason}"
        for item in broken
    ]
    assert not broken, "Broken documentation links found:\n" + "\n".join(failures)


def test_check_doc_links_cli() -> None:
    """CLI tool runs cleanly with --check."""
    assert checker.main(["--check"]) == 0


def test_link_validation_detects_broken_targets(tmp_path: Path) -> None:
    """Link checker detects missing files, broken anchors, and personal file:// URIs."""
    doc = tmp_path / "sample.md"
    doc.write_text(
        "# Heading\n\n"
        "[good link](#heading)\n"
        "[bad anchor](#nonexistent)\n"
        "[missing file](nonexistent.md)\n"
        "[forbidden uri](file:///home/user/path)\n"
        "[external ok](https://example.com)\n",
        encoding="utf-8",
    )

    _, broken = checker.check_file_links(doc, tmp_path, {})
    reasons = {b.target: b.reason for b in broken}

    assert "#nonexistent" in reasons
    assert "nonexistent.md" in reasons
    assert "file:///home/user/path" in reasons
    assert "https://example.com" not in reasons
    assert "#heading" not in reasons
