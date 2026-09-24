"""Refresh Call of Pripyat item/upgrade names in web/catalogs.json.

The bundled CoP snapshot was generated while the catalog loader preferred
``text/eng``, so most names were English and many weapons had none.  This tool
re-derives names from an unpacked *original* CoP ``gamedata`` tree with the
editor's own X-Ray parsers (``inv_name`` + Russian string tables) and changes
names only: keys, icons and serializer metadata stay as generated.

    python3 tools/localize_cop_catalog.py /path/to/unpacked/gamedata

Community overlays (files matching the loader's mod markers) are skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editor.xray_catalog import (  # noqa: E402
    _KNOWN_MOD_MARKERS,
    _decode,
    _items_from_sections,
    _localization,
    _parse_ltx,
    _upgrades_from_sections,
)

CATALOG = ROOT / "web" / "catalogs.json"
RELEASE = "stalker-cop"


def derive_names(gamedata: Path) -> tuple[dict[str, str], dict[str, str]]:
    sections: dict = {}
    for path in sorted(gamedata.rglob("*.ltx"), key=lambda value: value.as_posix().casefold()):
        if any(marker in path.name.casefold() for marker in _KNOWN_MOD_MARKERS) or "ixray" in path.name:
            continue
        sections.update(_parse_ltx(_decode(path.read_bytes()), path.relative_to(gamedata).as_posix()))
    localization = _localization(gamedata)
    items = _items_from_sections(sections, localization)
    upgrades = _upgrades_from_sections(
        sections,
        localization,
        {item.key for item in items},
        release_id=RELEASE,
        source_root=gamedata,
    )
    item_names = {item.key: item.display_name for item in items if item.display_name}
    upgrade_names = {
        upgrade.key: upgrade.display_name
        for upgrade in (upgrades.upgrades if upgrades is not None else ())
        if upgrade.display_name and not upgrade.display_name.startswith("st_")
    }
    return item_names, upgrade_names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gamedata", type=Path)
    args = parser.parse_args(argv)
    item_names, upgrade_names = derive_names(args.gamedata.expanduser())
    document = json.loads(CATALOG.read_text(encoding="utf-8"))
    release = document["releases"][RELEASE]
    items = upgrades = 0
    for item in release["items"]:
        name = item_names.get(item["key"])
        if name and name != item.get("display_name"):
            item["display_name"] = name
            items += 1
    for upgrade in release.get("upgrades", []):
        name = upgrade_names.get(upgrade["key"])
        if name and name != upgrade.get("display_name"):
            upgrade["display_name"] = name
            upgrades += 1
    CATALOG.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{RELEASE}: renamed {items} items and {upgrades} upgrades", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
