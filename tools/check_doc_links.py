#!/usr/bin/env python3
"""Check relative markdown links in documentation and README.md.

Validates that all relative links and anchor fragments within documentation
and project files resolve to existing files and sections, preventing documentation
rot, broken references after file moves/renames, and non-portable personal paths.

Usage:
    python3 tools/check_doc_links.py
    python3 tools/check_doc_links.py --check
    python3 tools/check_doc_links.py --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

# Match inline markdown links: [text](target) or ![alt](target)
# Supports optional title attribute and angle brackets around target.
INLINE_LINK_RE = re.compile(
    r"!?\[((?:[^\]]|\\\])*)\]\(\s*<?([^\s\)>]+)>?(?:\s+[\"\x27](?:[^\x27\"]|\\\")*[\"\x27])?\s*\)"
)

# Match reference-style definitions: [ref]: target
REF_DEF_RE = re.compile(r"^\s*\[([^\]]+)\]:\s*<?([^\s>]+)>?", re.MULTILINE)

EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "ftp://", "irc://")


@dataclass(frozen=True)
class BrokenLink:
    file: Path
    line: int
    text: str
    target: str
    reason: str


def slugify_heading(text: str) -> str:
    """GitHub-compatible markdown heading slugification."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def extract_anchors(file_path: Path) -> set[str]:
    """Extract valid section anchor identifiers from a markdown file."""
    anchors: set[str] = set()
    if not file_path.is_file():
        return anchors
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return anchors

    # Mask fenced code blocks so headings in examples are not collected
    masked = re.sub(
        r"```.*?```|~~~.*?~~~",
        lambda m: "\n" * m.group(0).count("\n"),
        content,
        flags=re.DOTALL,
    )

    for line in masked.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            # Strip inline links if any from heading text
            clean_heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
            anchors.add(slugify_heading(clean_heading))
            anchors.add(clean_heading.lower())
        for m in re.finditer(r"<a\s+[^>]*(?:id|name)=[\"\x27]([^\x27\"]+)[\"\x27]", stripped, re.IGNORECASE):
            anchors.add(m.group(1).lower())
            anchors.add(slugify_heading(m.group(1)))
    return anchors


def find_markdown_files(root: Path) -> list[Path]:
    """Collect all markdown files to check: root README.md, docs/**/*.md, etc."""
    files: list[Path] = []
    readme = root / "README.md"
    if readme.is_file():
        files.append(readme)
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        files.extend(sorted(docs_dir.glob("**/*.md")))
    agents_md = root / "AGENTS.md"
    if agents_md.is_file():
        files.append(agents_md)
    return files


def check_file_links(file_path: Path, root: Path, anchor_cache: dict[Path, set[str]]) -> tuple[int, list[BrokenLink]]:
    """Scan a single markdown file for broken relative links and anchors."""
    content = file_path.read_text(encoding="utf-8")
    # Preserve newlines when masking code blocks to keep line numbers accurate
    masked_content = re.sub(
        r"```.*?```|~~~.*?~~~",
        lambda m: "\n" * m.group(0).count("\n"),
        content,
        flags=re.DOTALL,
    )

    broken: list[BrokenLink] = []
    link_count = 0

    # Inline links
    for m in INLINE_LINK_RE.finditer(masked_content):
        link_count += 1
        text = m.group(1).strip()
        raw_target = m.group(2).strip()
        line_no = masked_content[: m.start()].count("\n") + 1

        issue = _validate_target(raw_target, file_path, root, anchor_cache)
        if issue:
            broken.append(BrokenLink(
                file=file_path.relative_to(root),
                line=line_no,
                text=text,
                target=raw_target,
                reason=issue,
            ))

    # Reference definitions
    for m in REF_DEF_RE.finditer(masked_content):
        link_count += 1
        ref_id = m.group(1).strip()
        raw_target = m.group(2).strip()
        line_no = masked_content[: m.start()].count("\n") + 1

        issue = _validate_target(raw_target, file_path, root, anchor_cache)
        if issue:
            broken.append(BrokenLink(
                file=file_path.relative_to(root),
                line=line_no,
                text=f"ref:{ref_id}",
                target=raw_target,
                reason=issue,
            ))

    return link_count, broken


def _validate_target(
    raw_target: str,
    file_path: Path,
    root: Path,
    anchor_cache: dict[Path, set[str]],
) -> str | None:
    if not raw_target:
        return "empty link target"

    if raw_target.startswith(EXTERNAL_SCHEMES):
        return None

    if raw_target.startswith("file://"):
        return "personal non-portable file:// URI (must use relative repository path)"

    # Internal anchor link within the current file
    if raw_target.startswith("#"):
        anchor = raw_target.lstrip("#")
        if file_path not in anchor_cache:
            anchor_cache[file_path] = extract_anchors(file_path)
        valid = anchor_cache[file_path]
        if anchor.lower() not in valid and slugify_heading(anchor) not in valid:
            return f"anchor '#{anchor}' not found in {file_path.name}"
        return None

    # Separate file part from optional anchor or query
    clean_target = unquote(raw_target.split("#")[0].split("?")[0])
    target_anchor = raw_target.split("#")[1] if "#" in raw_target else None

    if not clean_target:
        return None

    if clean_target.startswith("/"):
        dest = (root / clean_target.lstrip("/")).resolve()
    else:
        dest = (file_path.parent / clean_target).resolve()

    if not dest.exists():
        return f"target path does not exist: {dest}"

    # If anchor specified and target is a markdown document, verify anchor
    if target_anchor and dest.suffix == ".md" and dest.is_file():
        if dest not in anchor_cache:
            anchor_cache[dest] = extract_anchors(dest)
        valid = anchor_cache[dest]
        if target_anchor.lower() not in valid and slugify_heading(target_anchor) not in valid:
            return f"anchor '#{target_anchor}' not found in {dest.name}"

    return None


def find_broken_links(root: Path | None = None) -> list[BrokenLink]:
    """Scan all documentation files and return any broken links."""
    base_root = (root or ROOT).resolve()
    files = find_markdown_files(base_root)
    anchor_cache: dict[Path, set[str]] = {}
    all_broken: list[BrokenLink] = []

    for file_path in files:
        _, broken = check_file_links(file_path, base_root, anchor_cache)
        all_broken.extend(broken)

    return all_broken


def check_all(
    root: Path | None = None,
    verbose: bool = False,
) -> tuple[int, int, list[BrokenLink]]:
    """Scan all documentation files and return (total_files, total_links, broken_links)."""
    base_root = (root or ROOT).resolve()
    files = find_markdown_files(base_root)
    anchor_cache: dict[Path, set[str]] = {}
    all_broken: list[BrokenLink] = []
    total_links = 0

    for file_path in files:
        count, broken = check_file_links(file_path, base_root, anchor_cache)
        total_links += count
        all_broken.extend(broken)
        if verbose:
            rel = file_path.relative_to(base_root)
            status = f"FAILED ({len(broken)} broken)" if broken else "OK"
            print(f"  {rel} ({count} links) -> {status}")

    return len(files), total_links, all_broken


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if any broken link is found")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print details of each file checked")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root directory to scan")
    args = parser.parse_args(argv)

    total_files, total_links, broken = check_all(root=args.root, verbose=args.verbose)

    if broken:
        print(f"\nFound {len(broken)} broken link(s) across {total_files} files ({total_links} checked):\n")
        for item in broken:
            print(f"  {item.file}:{item.line}: [{item.text}]({item.target})")
            print(f"    Error: {item.reason}")
        return 1

    print(f"check_doc_links: checked {total_files} markdown files, {total_links} links — all valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
