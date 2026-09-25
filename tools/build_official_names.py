#!/usr/bin/env python3
"""Snapshot official item, upgrade and community names in every language.

The 2025 Enhanced Editions ship the trilogy's string tables in thirteen
languages.  This tool reads them from installed Enhanced Editions (packed
``resources/configs.db``) and writes ``web/catalog_names.json``: for each
release family, section key → {interface language → official name}.  Only
names are kept — no descriptions, prototypes or serializer data — so the
snapshot can never change what the editor is allowed to write.

Usage:
    python tools/build_official_names.py [--steam-common DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from editor.xray_catalog import (  # noqa: E402
    _decode,
    _items_from_sections,
    _parse_ltx,
    _read_xray_archive,
    _resolve_sections,
    _upgrades_from_sections,
)
from editor.xray_factions import factions_from_sections  # noqa: E402

OUTPUT = ROOT / "web" / "catalog_names.json"
DEFAULT_COMMON = Path.home() / ".local" / "share" / "Steam" / "steamapps" / "common"

# Install folder → release family used by the editor.
GAMES = (
    ("soc", "STALKER Shadow of Chornobyl - EE"),
    ("clear_sky", "STALKER Clear Sky - EE"),
    ("cop", "STALKER Call of Prypiat - EE"),
)

# Text folder → (interface language, the codepage the engine really uses).
# Every file declares windows-1251, but the Enhanced Editions render each
# language with its own codepage and the CJK tables are UTF-8.
LANGUAGES = {
    "rus": ("ru", "cp1251"),
    "ukr": ("uk", "cp1251"),
    "eng": ("en", "cp1252"),
    "ger": ("de", "cp1252"),
    "fra": ("fr", "cp1252"),
    "ita": ("it", "cp1252"),
    "spa": ("es", "cp1252"),
    "pol": ("pl", "cp1250"),
    "cze": ("cs", "cp1250"),
    "jpn": ("ja", "utf-8"),
    "kor": ("ko", "utf-8"),
    "zh_cn": ("zh_CN", "utf-8"),
    "zh_tw": ("zh_TW", "utf-8"),
}

_DECLARATION = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)


def _strings(data: bytes, codepage: str) -> dict[str, str]:
    try:
        text = data.decode(codepage)
    except UnicodeDecodeError:
        text = data.decode(codepage, errors="replace")
    try:
        tree = ET.fromstring(_DECLARATION.sub("", text.lstrip("﻿"), count=1))
    except ET.ParseError:
        return {}
    values: dict[str, str] = {}
    for element in tree.iter("string"):
        key = element.attrib.get("id")
        node = element.find("text")
        value = node.text.strip() if node is not None and node.text else ""
        if key and value:
            values[key] = value
    return values


def _usable(name: str | None, key: str) -> str | None:
    if not name:
        return None
    name = " ".join(name.split())
    # A missing translation leaves the string id itself behind.
    if name == key or name.casefold().startswith(("st_", "up_", "ui_st_")):
        return None
    return name


def harvest(common: Path) -> dict[str, dict[str, dict[str, dict[str, str]]]]:
    releases: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    for family, folder in GAMES:
        archive = common / folder / "resources" / "configs.db"
        if not archive.is_file():
            raise SystemExit(f"missing {archive}")
        files = _read_xray_archive(archive)
        sections = {}
        for name, raw in sorted(files.items()):
            if name.casefold().endswith(".ltx"):
                sections.update(_parse_ltx(_decode(raw), name))
        tables: dict[str, dict[str, dict[str, str]]] = {"items": {}, "upgrades": {}, "factions": {}}
        for text_folder, (language, codepage) in LANGUAGES.items():
            localization: dict[str, str] = {}
            for name, raw in files.items():
                normalized = name.replace("\\", "/").casefold()
                if f"/text/{text_folder}/" in f"/{normalized}" and normalized.endswith(".xml"):
                    localization.update(_strings(raw, codepage))
            if not localization:
                continue
            items = _items_from_sections(sections, localization)
            for item in items:
                label = _usable(item.display_name, item.key)
                if label:
                    tables["items"].setdefault(item.key, {})[language] = label
            upgrades = _upgrades_from_sections(
                sections,
                localization,
                {item.key for item in items},
                release_id=f"stalker-{family}",
                source_root=None,
            )
            for upgrade in upgrades.upgrades if upgrades is not None else ():
                label = _usable(upgrade.display_name, upgrade.key)
                if label:
                    tables["upgrades"].setdefault(upgrade.key, {})[language] = label
            factions = factions_from_sections(
                _resolve_sections(sections), localization, release_id=f"stalker-{family}"
            )
            for faction in factions.factions if factions is not None else ():
                label = _usable(faction.display_name, faction.key)
                if label:
                    tables["factions"].setdefault(faction.key, {})[language] = label
        tables["_keys"] = {item.key: {} for item in _items_from_sections(sections, {})}
        releases[family] = tables
    _borrow_missing_names(releases)
    return {
        family: {
            kind: {key: dict(sorted(names.items())) for key, names in sorted(rows.items())}
            for kind, rows in tables.items()
            if not kind.startswith("_")
        }
        for family, tables in releases.items()
    }


def _borrow_missing_names(releases) -> None:
    """Fill an item a game ships without any name from a sibling game.

    Clear Sky's ``wpn_binoc`` points at a string the game never defines; the
    same section in the other two games is the same binoculars.  Existing
    names are never replaced.
    """

    for family, tables in releases.items():
        for key in tables["_keys"]:
            if key in tables["items"]:
                continue
            for other, other_tables in releases.items():
                if other != family and key in other_tables["items"]:
                    tables["items"][key] = dict(other_tables["items"][key])
                    break


def render(releases) -> str:
    payload = {
        "schema_version": 1,
        "source": "S.T.A.L.K.E.R. Enhanced Edition string tables (names only)",
        "languages": sorted({language for language, _codepage in LANGUAGES.values()}),
        "releases": releases,
    }
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--steam-common", type=Path, default=DEFAULT_COMMON)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    text = render(harvest(args.steam_common.expanduser()))
    args.output.write_text(text, encoding="utf-8")
    data = json.loads(text)
    for family, tables in data["releases"].items():
        print(family, {kind: len(rows) for kind, rows in tables.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
