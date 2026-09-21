"""Read-only metadata catalog for loose S.T.A.L.K.E.R. 2 resources.

S.T.A.L.K.E.R. 2 keeps its gameplay prototypes in Unreal-style ``.cfg``
structures.  The canonical path consumes only loose files under the official
``Content/GameLite/GameData`` tree.  An explicitly selected Zone Kit or
Workshop tree can be read as provenance-labeled catalog research data, but
the reader does not unpack PAK files or claim that an Unreal prototype SID is
the compact key stored in a save.  The latter mapping and every S2 save writer
remain separate evidence gates.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .catalog import (
    FactionCatalog,
    GameCatalog,
    ItemCatalog,
    ItemDefinition,
    UpgradeCatalog,
    UpgradeDefinition,
)
from .releases import ReleaseDescriptor, release_by_id

_MOD_PARTS = frozenset(
    {
        "~mods",
        "mods",
        "savedmods",
        "pak__mods",
        "s2zonamods",
        "anomaly",
        "misery",
        "ogsm",
    }
)
_ITEM_FIELDS = frozenset(
    {
        "type",
        "itemtype",
        "itemslottype",
        "weight",
        "maxstackcount",
        "maxstack",
        "displayname",
        "display_name",
        "icon",
        "iconpath",
        "icontexture",
        "inventoryicon",
    }
)
_CATEGORY_BY_FILE = {
    "ammo": "ammo",
    "armor": "outfit",
    "artifact": "artifact",
    "attach": "attachment",
    "consumable": "consumable",
    "detector": "detector",
    "grenade": "grenade",
    "keyitem": "quest",
    "questitem": "quest",
    "weapon": "weapon",
}
_UPGRADE_KEY_RE = re.compile(r"upgrade.*sids?$", re.IGNORECASE)
_REFKEY_RE = re.compile(r"\brefkey\s*=\s*([^;}]+)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_S2_APP_ID = release_by_id("stalker2").app_id
_ZONE_KIT_ENV_KEYS = ("STALKER2_ZONE_KIT_ROOT", "ZONE_KIT_ROOT")
_WORKSHOP_ENV_KEYS = ("STALKER2_WORKSHOP_ROOT",)


class S2CatalogError(ValueError):
    """A malformed loose S2 config file."""


@dataclass(frozen=True)
class S2CatalogSource:
    """One explicitly discoverable loose metadata source.

    ``official`` and ``zonekit`` sources are read through the canonical
    parser.  ``workshop`` is deliberately a separate opt-in source because a
    mod overlay can override the game's prototypes and must never silently
    become authoritative save metadata.
    """

    root: Path
    kind: Literal["official", "zonekit", "workshop"]

    def __post_init__(self) -> None:
        root = Path(self.root).expanduser()
        object.__setattr__(self, "root", root)
        if self.kind not in {"official", "zonekit", "workshop"}:
            raise ValueError(f"unsupported S2 catalog source kind: {self.kind!r}")


@dataclass
class _S2Record:
    name: str
    source: str
    refkey: str | None = None
    values: dict[str, list[str]] = field(default_factory=dict)

    def add(self, key: str, value: str, context: tuple[str, ...] = ()) -> None:
        path = (*context, key) if context else (key,)
        self.values.setdefault("::".join(path).casefold(), []).append(value)


@dataclass
class _UpgradeRow:
    category: str | None
    source: str
    display_name: str | None = None
    items: set[str] = field(default_factory=set)


def _strip_comment(line: str) -> str:
    quote: str | None = None
    index = 0
    while index < len(line):
        character = line[index]
        if character in "\"'":
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
        elif quote is None:
            if character == ";":
                return line[:index]
            if character == "/" and index + 1 < len(line) and line[index + 1] == "/":
                return line[:index]
        index += 1
    return line


def _begin_name(line: str) -> str:
    left = line.split(":", 1)[0].strip()
    return left if left and left.casefold() != "struct.begin" else ""


def _begin_refkey(line: str) -> str | None:
    match = _REFKEY_RE.search(line)
    if match is None:
        return None
    value = match.group(1).strip().strip("\"'")
    return value or None


def _parse_cfg(text: str, source: str) -> tuple[_S2Record, ...]:
    records: list[_S2Record] = []
    active: _S2Record | None = None
    contexts: list[str] = []
    depth = 0
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw_line).strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.casefold()
        if "struct.begin" in lowered:
            if depth == 0:
                active = _S2Record(
                    name=_begin_name(line),
                    source=source,
                    refkey=_begin_refkey(line),
                )
                records.append(active)
            contexts.append(_begin_name(line))
            depth += 1
            continue
        if lowered.startswith("struct.end"):
            if depth == 0:
                raise S2CatalogError(f"{source}:{line_number}: лишний struct.end")
            depth -= 1
            if contexts:
                contexts.pop()
            if depth == 0:
                active = None
            continue
        if active is None or depth == 0 or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'").strip()
        if key and value:
            active.add(key, value, tuple(contexts[1:]))

    if depth != 0:
        raise S2CatalogError(f"{source}: незакрытый struct.begin")
    return tuple(records)


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _is_mod_path(path: Path) -> bool:
    return any(part.casefold() in _MOD_PARTS for part in path.parts)


def _resolved_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    try:
        return path.resolve()
    except OSError:
        return path


def _environment_paths(
    environ: Mapping[str, str],
    keys: Sequence[str],
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for key in keys:
        raw = environ.get(key, "")
        for value in raw.split(os.pathsep):
            if value.strip():
                paths.append(_resolved_path(value.strip()))
    return tuple(paths)


def _append_source(
    sources: list[S2CatalogSource],
    seen: set[tuple[Path, str]],
    root: str | Path,
    kind: Literal["official", "zonekit", "workshop"],
) -> None:
    path = _resolved_path(root)
    try:
        if not path.is_dir():
            return
    except OSError:
        return
    key = (path, kind)
    if key in seen:
        return
    seen.add(key)
    sources.append(S2CatalogSource(path, kind))


def _workshop_item_roots(root: str | Path) -> tuple[Path, ...]:
    """Return Steam Workshop item directories below one library override."""

    path = _resolved_path(root)
    if not path.is_dir():
        return ()
    if (path / "Content").is_dir() or (path / "Stalker2").is_dir():
        return (path,)
    library_content_root = path / "steamapps" / "workshop" / "content" / str(_S2_APP_ID)
    if library_content_root.is_dir():
        content_root = library_content_root
    elif path.name == str(_S2_APP_ID):
        content_root = path
    elif (path / str(_S2_APP_ID)).is_dir():
        content_root = path / str(_S2_APP_ID)
    elif path.name.isdigit() and path.parent.name == str(_S2_APP_ID):
        return (path,)
    else:
        content_root = path
    try:
        return tuple(
            child
            for child in sorted(content_root.iterdir(), key=lambda item: item.name.casefold())
            if child.is_dir() and not child.is_symlink()
        )
    except OSError:
        return ()


def discover_s2_catalog_sources(
    source_name: str | None = None,
    *,
    installed_roots: Iterable[str | Path] = (),
    steam_libraries: Iterable[str | Path] = (),
    environ: Mapping[str, str] | None = None,
) -> tuple[S2CatalogSource, ...]:
    """Discover loose S2 metadata without treating mods as canonical.

    The source path and installed roots are searched first.  Zone Kit roots
    are explicit environment overrides.  Steam Workshop directories are
    included last and are only usable through :meth:`load_overlay`, so an
    overlay cannot shadow an official catalog by accident.
    """

    sources: list[S2CatalogSource] = []
    seen: set[tuple[Path, str]] = set()
    if source_name:
        source_path = Path(source_name).expanduser()
        if source_path.is_absolute() or source_path.exists():
            try:
                source_path = source_path.resolve()
            except OSError:
                pass
            start = source_path.parent if source_path.is_file() else source_path
            for source_root in (start, *start.parents):
                _append_source(sources, seen, source_root, "official")

    for installed_root in installed_roots:
        _append_source(sources, seen, installed_root, "official")

    env = os.environ if environ is None else environ
    for zonekit_root in _environment_paths(env, _ZONE_KIT_ENV_KEYS):
        _append_source(sources, seen, zonekit_root, "zonekit")

    workshop_roots = list(_environment_paths(env, _WORKSHOP_ENV_KEYS))
    workshop_roots.extend(_resolved_path(library) for library in steam_libraries)
    for root in workshop_roots:
        for item_root in _workshop_item_roots(root):
            _append_source(sources, seen, item_root, "workshop")
    return tuple(sources)


def _effective_values(
    record: _S2Record,
    by_reference: dict[str, _S2Record],
    cache: dict[int, dict[str, tuple[str, ...]]],
    stack: tuple[int, ...] = (),
) -> dict[str, tuple[str, ...]]:
    identity = id(record)
    if identity in cache:
        return cache[identity]
    if identity in stack:
        return {}
    values: dict[str, tuple[str, ...]] = {}
    if record.refkey:
        base = by_reference.get(record.refkey.casefold())
        if base is not None:
            values.update(_effective_values(base, by_reference, cache, (*stack, identity)))
    values.update({key: tuple(items) for key, items in record.values.items()})
    cache[identity] = values
    return values


def _first(values: dict[str, tuple[str, ...]], *keys: str) -> str | None:
    for key in keys:
        entries = values.get(key.casefold())
        if entries:
            return entries[0]
    wanted = {key.casefold() for key in keys}
    for path, entries in values.items():
        if path.rsplit("::", 1)[-1] in wanted and entries:
            return entries[0]
    return None


def _record_first(record: _S2Record, key: str) -> str | None:
    entries = record.values.get(key.casefold())
    return entries[0] if entries else None


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    match = _NUMBER_RE.search(value)
    if match is None:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _integer(value: str | None) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer() or number < 0:
        return None
    return int(number)


def _enum_leaf(value: str) -> str | None:
    value = value.strip().strip("\"'")
    if "::" in value:
        value = value.rsplit("::", 1)[-1]
    value = value.strip()
    return None if value.casefold() in {"", "none", "null"} else value


def _slots(values: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    result: list[str] = []
    for key in ("itemslottype", "itemslottypes"):
        for value in (
            entry
            for path, entries in values.items()
            if path.rsplit("::", 1)[-1] == key
            for entry in entries
        ):
            for token in re.split(r"[,;]", value):
                item = _enum_leaf(token)
                if item is not None and item not in result:
                    result.append(item)
    return tuple(result)


def _category(record: _S2Record, values: dict[str, tuple[str, ...]]) -> str | None:
    type_value = _first(values, "type", "itemtype", "prototypeclass")
    lowered = (type_value or "").casefold()
    for token, category in (
        ("weapon", "weapon"),
        ("armor", "outfit"),
        ("outfit", "outfit"),
        ("artifact", "artifact"),
        ("ammo", "ammo"),
        ("consum", "consumable"),
        ("grenade", "grenade"),
        ("detector", "detector"),
        ("attach", "attachment"),
        ("quest", "quest"),
        ("keyitem", "quest"),
    ):
        if token in lowered:
            return category
    filename = record.source.rsplit("/", 1)[-1].casefold()
    for token, category in _CATEGORY_BY_FILE.items():
        if token in filename:
            return category
    return "item"


def _is_item(record: _S2Record, values: dict[str, tuple[str, ...]]) -> bool:
    leaves = {path.rsplit("::", 1)[-1] for path in values}
    # SID is the record identity, not an arbitrary nested metadata field.
    # Requiring the top-level key prevents a nested attachment/property SID
    # from becoming a selectable item definition by accident.
    return bool(record.values.get("sid")) and bool(_ITEM_FIELDS & leaves)


def _display_name(values: dict[str, tuple[str, ...]]) -> str | None:
    value = _first(
        values,
        "displayname",
        "display_name",
        "localizedname",
        "itemname",
    )
    if value is None:
        return None
    normalized = value.strip().strip("\"'")
    return normalized or None


def _icon_texture(values: dict[str, tuple[str, ...]]) -> str | None:
    value = _first(
        values,
        "icon",
        "iconpath",
        "icontexture",
        "inventoryicon",
        "itemicon",
    )
    if value is None:
        return None
    normalized = value.strip().strip("\"'")
    return normalized or None


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.findall(r"[A-Za-z0-9_./-]+", value)
        if token.casefold() not in {"none", "null", "empty"}
    )


def _sids(values: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    result: list[str] = []
    for key, entries in values.items():
        path_parts = key.split("::")
        if not any(_UPGRADE_KEY_RE.fullmatch(part) for part in path_parts):
            continue
        for entry in entries:
            for token in _tokens(entry):
                if token in result:
                    continue
                result.append(token)
    return tuple(result)


def _item_sids(values: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    result: list[str] = []
    for key, entries in values.items():
        leaf = key.rsplit("::", 1)[-1]
        if leaf not in {"itemprototypesid", "itemprototypesids"}:
            continue
        for entry in entries:
            for token in _tokens(entry):
                if token not in result:
                    result.append(token)
    return tuple(result)


def _source(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _find_game_data(root: Path, *, allow_mod_path: bool = False) -> Path | None:
    candidates: list[Path] = [
        root / "Content" / "GameLite" / "GameData",
        root / "Stalker2" / "Content" / "GameLite" / "GameData",
        root / "stalker2" / "Content" / "GameLite" / "GameData",
    ]
    if root.name.casefold() == "gamedata":
        candidates.insert(0, root)
    for candidate in candidates:
        if candidate.is_dir() and (allow_mod_path or not _is_mod_path(candidate)):
            return candidate
    if not allow_mod_path:
        return None
    try:
        nested_candidates = sorted(
            (
                path
                for path in root.rglob("GameData")
                if path.is_dir()
                and not path.is_symlink()
                and tuple(part.casefold() for part in path.parts[-3:])
                == ("content", "gamelite", "gamedata")
            ),
            key=lambda item: item.as_posix().casefold(),
        )
    except OSError:
        return None
    if nested_candidates:
        return nested_candidates[0]
    return None


def _catalog_source_root(root: Path, game_data: Path) -> Path:
    """Return the content root from which loose image assets are addressable."""

    if root.name.casefold() == "gamedata":
        return root
    if tuple(part.casefold() for part in game_data.parts[-3:]) == (
        "content",
        "gamelite",
        "gamedata",
    ):
        return game_data.parents[2]
    return root


class S2CatalogProvider:
    """Load loose S2 prototype metadata without save semantics."""

    def __init__(self) -> None:
        self._catalog: ItemCatalog | None = None
        self._game_catalog: GameCatalog | None = None

    def load(
        self,
        release: ReleaseDescriptor,
        game_root: Path | None = None,
    ) -> ItemCatalog | None:
        """Load canonical official metadata and reject mod overlays."""

        return self._load(release, game_root, allow_mod_overlay=False)

    def load_overlay(
        self,
        release: ReleaseDescriptor,
        game_root: Path | None = None,
    ) -> ItemCatalog | None:
        """Load one explicitly selected loose Workshop/mod metadata tree.

        This is catalog-only research data. It never changes the selected
        save format capabilities and it is never merged into an official
        catalog implicitly.
        """

        return self._load(release, game_root, allow_mod_overlay=True)

    def _load(
        self,
        release: ReleaseDescriptor,
        game_root: Path | None,
        *,
        allow_mod_overlay: bool,
    ) -> ItemCatalog | None:
        self._catalog = None
        self._game_catalog = None
        if release.family != "stalker2" or release.edition != "s2" or game_root is None:
            return None
        root = Path(game_root).expanduser()
        if not root.is_dir() or (not allow_mod_overlay and _is_mod_path(root)):
            return None
        game_data = _find_game_data(root, allow_mod_path=allow_mod_overlay)
        if game_data is None:
            return None
        item_root = game_data / "ItemPrototypes"
        if not item_root.is_dir() or (
            not allow_mod_overlay and _is_mod_path(item_root)
        ):
            return None

        item_paths = tuple(
            path
            for path in sorted(item_root.rglob("*.cfg"), key=lambda item: item.as_posix().casefold())
            if path.is_file()
            and not path.is_symlink()
            and (allow_mod_overlay or not _is_mod_path(path))
        )
        records: list[_S2Record] = []
        for path in item_paths:
            try:
                records.extend(_parse_cfg(_read_text(path), _source(root, path)))
            except (OSError, S2CatalogError):
                continue
        if not records:
            return None

        upgrade_paths = tuple(
            path
            for path in sorted(game_data.rglob("*.cfg"), key=lambda item: item.as_posix().casefold())
            if path.is_file()
            and not path.is_symlink()
            and (allow_mod_overlay or not _is_mod_path(path))
            and "upgrade" in path.as_posix().casefold()
            and path not in item_paths
        )
        upgrade_records_by_path: list[tuple[Path, tuple[_S2Record, ...]]] = []
        for path in upgrade_paths:
            try:
                parsed = _parse_cfg(_read_text(path), _source(root, path))
            except (OSError, S2CatalogError):
                continue
            if parsed:
                upgrade_records_by_path.append((path, parsed))

        by_reference: dict[str, _S2Record] = {}
        for record in (*records, *(record for _, parsed in upgrade_records_by_path for record in parsed)):
            by_reference.setdefault(record.name.casefold(), record)
            sid = _record_first(record, "sid")
            if sid:
                by_reference.setdefault(sid.casefold(), record)
        cache: dict[int, dict[str, tuple[str, ...]]] = {}
        items: list[ItemDefinition] = []
        item_by_sid: dict[str, ItemDefinition] = {}
        item_upgrade_refs: dict[str, set[str]] = {}
        for record in records:
            values = _effective_values(record, by_reference, cache)
            sid = _first(values, "sid")
            if sid is None or not _is_item(record, values) or sid in item_by_sid:
                continue
            definition = ItemDefinition(
                key=sid,
                display_name=_display_name(values),
                category=_category(record, values),
                unit_weight=_number(_first(values, "weight")),
                width=None,
                height=None,
                max_stack=_integer(_first(values, "maxstackcount", "maxstack")),
                slots=_slots(values),
                prototype=None,
                source=f"{record.source}#{record.name or sid}",
                serialization_family=None,
                icon_texture=_icon_texture(values),
            )
            items.append(definition)
            item_by_sid[sid] = definition
            item_upgrade_refs[sid] = set(_sids(values))
        if not items:
            return None

        source_root = _catalog_source_root(root, game_data)
        item_catalog = ItemCatalog(release.id, source_root, tuple(items))
        upgrade_rows: dict[str, _UpgradeRow] = {}
        for item_sid, upgrade_sids in item_upgrade_refs.items():
            for upgrade_sid in upgrade_sids:
                row = upgrade_rows.setdefault(
                    upgrade_sid,
                    _UpgradeRow(
                        category=item_by_sid[item_sid].category,
                        source=item_by_sid[item_sid].source,
                    ),
                )
                row.items.add(item_sid)

        for _, upgrade_records in upgrade_records_by_path:
            for record in upgrade_records:
                values = _effective_values(record, by_reference, cache)
                sid = _first(values, "sid")
                if sid is None:
                    continue
                row = upgrade_rows.setdefault(
                    sid,
                    _UpgradeRow(
                        category=_category(record, values),
                        source=f"{record.source}#{record.name or sid}",
                        display_name=_display_name(values),
                    ),
                )
                if row.display_name is None:
                    row.display_name = _display_name(values)
                for item_sid in _item_sids(values):
                    if item_sid in item_by_sid:
                        row.items.add(item_sid)

        upgrades = (
            UpgradeCatalog(
                release.id,
                source_root,
                tuple(
                    UpgradeDefinition(
                        key=key,
                        display_name=row.display_name,
                        category=row.category,
                        item_key=(
                            sorted(row.items)[0]
                            if row.items
                            else None
                        ),
                        source=row.source,
                        release_id=release.id,
                        applicable_item_keys=tuple(sorted(row.items)),
                    )
                    for key, row in sorted(upgrade_rows.items(), key=lambda item: item[0].casefold())
                ),
            )
            if upgrade_rows
            else None
        )
        empty_factions = FactionCatalog(release.id, source_root, ())
        self._catalog = item_catalog
        self._game_catalog = GameCatalog(release.id, item_catalog, empty_factions, upgrades)
        return item_catalog

    def load_bundle(
        self,
        release: ReleaseDescriptor,
        game_root: Path | None = None,
    ) -> GameCatalog | None:
        """Load item/upgrade metadata with an intentionally empty faction catalog."""

        self.load(release, game_root)
        return self._game_catalog

    def load_overlay_bundle(
        self,
        release: ReleaseDescriptor,
        game_root: Path | None = None,
    ) -> GameCatalog | None:
        """Load one explicit Workshop/mod tree as a catalog-only bundle."""

        self.load_overlay(release, game_root)
        return self._game_catalog

    def resolve(self, key: str) -> ItemDefinition | None:
        return self._catalog.resolve(key) if self._catalog is not None else None


__all__ = [
    "S2CatalogError",
    "S2CatalogProvider",
    "S2CatalogSource",
    "discover_s2_catalog_sources",
]
