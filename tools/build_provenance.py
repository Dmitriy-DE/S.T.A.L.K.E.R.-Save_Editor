#!/usr/bin/env python3
"""Build the source and generator manifest for bundled visual assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor"
TRILOGY_EE = (
    "https://store.steampowered.com/app/2427430/"
    "STALKER_Call_of_Prypiat__Enhanced_Edition/"
)
S2_GAME = "https://store.steampowered.com/app/1643320/S.T.A.L.K.E.R._2_Heart_of_Chornobyl/"
S2_WIKI = "https://stalker.fandom.com/wiki/S.T.A.L.K.E.R._2:_Heart_of_Chornobyl"
S2_SOURCES = Path("data/s2_sources.json")

Basis = Literal["own", "ofl", "game-derived", "wiki-cc-by-sa", "fextralife"]


class ProvenanceRecord(TypedDict):
    source: str
    origin_url: str
    basis: Basis
    generator: str | None


def _record(
    source: str,
    origin_url: str,
    basis: Basis,
    generator: str | None = None,
) -> ProvenanceRecord:
    return {
        "source": source,
        "origin_url": origin_url,
        "basis": basis,
        "generator": generator,
    }


_RULES: tuple[tuple[str, ProvenanceRecord], ...] = (
    (
        "assets/PROVENANCE.json",
        _record(
            "Project asset provenance manifest",
            f"{REPOSITORY}/blob/main/assets/PROVENANCE.json",
            "own",
            "tools/build_provenance.py",
        ),
    ),
    (
        "assets/app_icon.svg",
        _record(
            "S.T.A.L.K.E.R. Save Editor application icon",
            f"{REPOSITORY}/blob/main/assets/app_icon.svg",
            "own",
        ),
    ),
    (
        "assets/app_icon_*.png",
        _record(
            "Raster exports of the S.T.A.L.K.E.R. Save Editor application icon",
            f"{REPOSITORY}/blob/main/assets/app_icon.svg",
            "own",
        ),
    ),
    (
        "assets/chrome/xray/*.png",
        _record(
            "S.T.A.L.K.E.R. trilogy Enhanced Edition ui_common atlas",
            TRILOGY_EE,
            "game-derived",
            "tools/build_chrome_pack.py",
        ),
    ),
    (
        "assets/sounds/game/*/*.ogg",
        _record(
            "S.T.A.L.K.E.R. trilogy menu music and interface sounds (original and Enhanced Edition archives)",
            TRILOGY_EE,
            "game-derived",
            "ui/game_audio.py (extract_files)",
        ),
    ),
    (
        "assets/fonts/LIBERATION-SANS-LICENSE.txt",
        _record(
            "Liberation Fonts project; SIL Open Font License 1.1",
            "https://github.com/liberationfonts",
            "ofl",
        ),
    ),
    (
        "assets/fonts/LiberationSansNarrow-*.ttf",
        _record(
            "Liberation Sans Narrow; SIL Open Font License 1.1",
            "https://github.com/liberationfonts",
            "ofl",
        ),
    ),
    (
        "assets/fonts/Oswald*.ttf",
        _record(
            "Oswald from Google Fonts; SIL Open Font License 1.1",
            "https://github.com/google/fonts/tree/main/ofl/oswald",
            "ofl",
        ),
    ),
    (
        "assets/fonts/Oswald-OFL.txt",
        _record(
            "Oswald license text from Google Fonts",
            "https://github.com/google/fonts/tree/main/ofl/oswald",
            "ofl",
        ),
    ),
    (
        "assets/icons/xray/*.png",
        _record(
            "S.T.A.L.K.E.R. trilogy Enhanced Edition ui_icon_equipment atlases",
            TRILOGY_EE,
            "game-derived",
            "tools/build_icon_pack.py",
        ),
    ),
    (
        "assets/icons/xray/index.json",
        _record(
            "Keys generated for the S.T.A.L.K.E.R. trilogy icon pack",
            TRILOGY_EE,
            "game-derived",
            "tools/build_icon_pack.py",
        ),
    ),
    (
        "assets/readme/*",
        _record(
            "S.T.A.L.K.E.R. Save Editor README artwork and screenshots",
            f"{REPOSITORY}/tree/main/assets/readme",
            "own",
        ),
    ),
    (
        "assets/ui/item_glyphs/*.svg",
        _record(
            "S.T.A.L.K.E.R. Save Editor item glyphs",
            f"{REPOSITORY}/tree/main/assets/ui/item_glyphs",
            "own",
        ),
    ),
    (
        "assets/ui/shell_icons/*.svg",
        _record(
            "S.T.A.L.K.E.R. Save Editor shell icons",
            f"{REPOSITORY}/tree/main/assets/ui/shell_icons",
            "own",
        ),
    ),
    (
        "assets/ui/s2_shell/amber_paper.png",
        _record(
            "Procedural amber paper UI texture",
            f"{REPOSITORY}/blob/main/tools/build_ui_review_decorations.py",
            "own",
            "tools/build_ui_review_decorations.py",
        ),
    ),
    (
        "assets/ui/s2_shell/selection_paper.png",
        _record(
            "Procedural selection paper UI texture",
            f"{REPOSITORY}/blob/main/tools/build_ui_review_decorations.py",
            "own",
            "tools/build_ui_review_decorations.py",
        ),
    ),
    (
        "assets/ui/s2_shell/surface_tile.png",
        _record(
            "S.T.A.L.K.E.R. Save Editor shell surface texture",
            f"{REPOSITORY}/tree/main/assets/ui/s2_shell",
            "own",
        ),
    ),
    (
        "assets/ui/s2_shell/header_panorama.png",
        _record(
            "S.T.A.L.K.E.R. 2 game imagery cropped into the editor header",
            S2_GAME,
            "game-derived",
            "tools/build_ui_review_decorations.py",
        ),
    ),
    (
        "assets/ui/s2_shell/preview_zone.png",
        _record(
            "S.T.A.L.K.E.R. 2 game imagery used by the editor library",
            S2_GAME,
            "game-derived",
        ),
    ),
    (
        "assets/ui/s2_shell/rail_zone.png",
        _record(
            "S.T.A.L.K.E.R. 2 game imagery used by the editor library",
            S2_GAME,
            "game-derived",
        ),
    ),
    (
        "web/icons/*.png",
        _record(
            "Mirrored S.T.A.L.K.E.R. trilogy Enhanced Edition inventory icons",
            TRILOGY_EE,
            "game-derived",
            "tools/build_icon_pack.py",
        ),
    ),
    (
        "web/icons/index.json",
        _record(
            "Keys generated for the mirrored S.T.A.L.K.E.R. trilogy icon pack",
            TRILOGY_EE,
            "game-derived",
            "tools/build_icon_pack.py",
        ),
    ),
)


def _asset_paths(root: Path) -> list[str]:
    paths: set[str] = set()
    for folder in (root / "assets", root / "web" / "icons"):
        if folder.exists():
            paths.update(
                path.relative_to(root).as_posix()
                for path in folder.rglob("*")
                if path.is_file()
            )
    return sorted(paths)


def _matching_paths(root: Path, pattern: str, asset_paths: set[str]) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.glob(pattern)
        if path.is_file()
    } & asset_paths


def _fextralife_sources(root: Path) -> dict[str, tuple[str, str]]:
    source_map = root / S2_SOURCES
    if not source_map.is_file():
        return {}

    raw: object = json.loads(source_map.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"S2 source map must be a JSON object: {S2_SOURCES}")

    sources: dict[str, tuple[str, str]] = {}
    for items in raw.values():
        if not isinstance(items, dict):
            continue
        for item_id, data in items.items():
            if (
                not isinstance(item_id, str)
                or not isinstance(data, list)
                or len(data) < 2
                or not isinstance(data[0], str)
                or not isinstance(data[1], str)
            ):
                continue
            parsed = urlparse(data[1])
            host = (parsed.hostname or "").casefold()
            is_fextralife = (
                host == "fextralife.com"
                or host.endswith(".fextralife.com")
                or host == "fextralifeimages.com"
                or host.endswith(".fextralifeimages.com")
            )
            if parsed.scheme != "https" or not is_fextralife:
                continue
            source = (data[0], data[1])
            previous = sources.setdefault(item_id, source)
            if previous != source:
                raise ValueError(f"conflicting Fextralife sources for S2 item: {item_id}")
    return sources


def _s2_record(path: str, sources: dict[str, tuple[str, str]]) -> ProvenanceRecord:
    item_id = Path(path).stem
    if item_id in sources:
        name, origin_url = sources[item_id]
        return _record(
            f"Fextralife item image: {name}",
            origin_url,
            "fextralife",
            "tools/build_s2_catalog.py",
        )
    return _record(
        "S.T.A.L.K.E.R. 2 wiki item media",
        S2_WIKI,
        "wiki-cc-by-sa",
        "tools/build_s2_catalog.py",
    )


def build_manifest(root: Path = ROOT) -> dict[str, ProvenanceRecord]:
    """Return active asset rules and fail if coverage is missing or ambiguous."""

    asset_paths = set(_asset_paths(root))
    manifest_path = "assets/PROVENANCE.json"
    # The manifest records itself even on the first build, before the file exists.
    asset_paths.add(manifest_path)

    records: dict[str, ProvenanceRecord] = {}
    for pattern, record in _RULES:
        matches = _matching_paths(root, pattern, asset_paths)
        if pattern == manifest_path:
            matches.add(manifest_path)
        if matches:
            records[pattern] = record

    s2_paths = sorted(
        path
        for path in asset_paths
        if path.startswith(("assets/icons/s2/", "web/icons/s2/"))
    )
    if s2_paths:
        sources = _fextralife_sources(root)
        for path in s2_paths:
            records[path] = _s2_record(path, sources)

    coverage: dict[str, list[str]] = {path: [] for path in asset_paths}
    for pattern in records:
        matches = _matching_paths(root, pattern, asset_paths)
        if pattern == manifest_path:
            matches.add(manifest_path)
        for path in matches:
            coverage[path].append(pattern)

    missing = sorted(path for path, patterns in coverage.items() if not patterns)
    ambiguous = sorted(path for path, patterns in coverage.items() if len(patterns) > 1)
    if missing or ambiguous:
        problems = []
        if missing:
            problems.append("unmapped assets: " + ", ".join(missing))
        if ambiguous:
            problems.append(
                "assets matched by multiple records: "
                + ", ".join(f"{path} ({', '.join(coverage[path])})" for path in ambiguous)
            )
        raise ValueError("; ".join(problems))

    return dict(sorted(records.items()))


def write_manifest(root: Path = ROOT) -> Path:
    records = build_manifest(root)
    output = root / "assets" / "PROVENANCE.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    args = parser.parse_args(argv)
    try:
        output = write_manifest(args.root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"wrote {output.relative_to(args.root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
