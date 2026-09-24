"""Load the compact official catalog shared by desktop and browser builds.

The generated browser catalog contains metadata derived from official X-Ray
resources, not game files or save bytes.  Keeping its decoder in the editor
package lets the desktop fallback and the browser bridge consume exactly the
same release-scoped data and validation rules.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .catalog import (
    FactionCatalog,
    FactionDefinition,
    GameCatalog,
    ItemCatalog,
    ItemDefinition,
    UpgradeCatalog,
    UpgradeDefinition,
    catalog_from_items,
)
from .releases import release_by_id


class CatalogBundleError(ValueError):
    """The generated catalog is malformed or contains foreign metadata."""


@dataclass(frozen=True)
class CatalogBundle:
    """All compact catalogs available for one official release."""

    release_id: str
    items: ItemCatalog
    factions: FactionCatalog | None = None
    upgrades: UpgradeCatalog | None = None

    def __post_init__(self) -> None:
        if self.items.release_id != self.release_id:
            raise CatalogBundleError("item catalog release_id does not match bundle")
        if self.factions is not None and self.factions.release_id != self.release_id:
            raise CatalogBundleError("faction catalog release_id does not match bundle")
        if self.upgrades is not None and self.upgrades.release_id != self.release_id:
            raise CatalogBundleError("upgrade catalog release_id does not match bundle")

    @property
    def game_catalog(self) -> GameCatalog | None:
        """Return the combined catalog only when faction metadata is present."""

        if self.factions is None:
            return None
        return GameCatalog(self.release_id, self.items, self.factions, self.upgrades)


def _optional_str(value: Any, field: str, release_id: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CatalogBundleError(f"Browser catalog: invalid {field} for {release_id!r}")
    return value


def _optional_int(value: Any, field: str, release_id: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise CatalogBundleError(f"Browser catalog: invalid {field} for {release_id!r}")
    return value


def _optional_float(value: Any, field: str, release_id: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CatalogBundleError(f"Browser catalog: invalid {field} for {release_id!r}")
    result = float(value)
    if not math.isfinite(result):
        raise CatalogBundleError(f"Browser catalog: invalid {field} for {release_id!r}")
    return result


def _optional_str_list(value: Any, field: str, release_id: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CatalogBundleError(f"Browser catalog: invalid {field} for {release_id!r}")
    return tuple(value)


def _document_from_payload(payload: str | bytes | bytearray | Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(payload, Mapping):
        document: Any = payload
    else:
        try:
            source = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
            document = json.loads(source)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise CatalogBundleError("Некорректный JSON browser catalog") from exc
    if not isinstance(document, Mapping) or document.get("schema_version") != 1:
        raise CatalogBundleError("Некорректная версия browser catalog")
    raw_releases = document.get("releases")
    if not isinstance(raw_releases, Mapping):
        raise CatalogBundleError("Browser catalog не содержит releases")
    return document


def load_catalog_payload(
    payload: str | bytes | bytearray | Mapping[str, object],
    *,
    source_root: Path | None = None,
) -> dict[str, CatalogBundle]:
    """Parse compact metadata and reject foreign release/catalog entries."""

    document = _document_from_payload(payload)
    raw_releases = document["releases"]
    assert isinstance(raw_releases, Mapping)
    loaded: dict[str, CatalogBundle] = {}
    for raw_release_id, raw_release in raw_releases.items():
        release_id = str(raw_release_id)
        try:
            descriptor = release_by_id(release_id)
        except KeyError as exc:
            raise CatalogBundleError(str(exc)) from exc
        if descriptor.edition not in {"original", "s2"}:
            raise CatalogBundleError(f"Browser catalog: unsupported release {release_id!r}")
        if not isinstance(raw_release, Mapping):
            raise CatalogBundleError(f"Browser catalog: invalid release {release_id!r}")

        raw_items = raw_release.get("items")
        if not isinstance(raw_items, list):
            raise CatalogBundleError(f"Browser catalog: invalid items for {release_id!r}")
        definitions: list[ItemDefinition] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, Mapping) or not isinstance(raw_item.get("key"), str):
                raise CatalogBundleError(f"Browser catalog: invalid item for {release_id!r}")
            key = raw_item["key"]
            assert isinstance(key, str)
            definitions.append(
                ItemDefinition(
                    key=key,
                    display_name=_optional_str(
                        raw_item.get("display_name"),
                        "item display_name",
                        release_id,
                    ),
                    category=_optional_str(raw_item.get("category"), "item category", release_id),
                    width=None,
                    height=None,
                    max_stack=_optional_int(raw_item.get("max_stack"), "item max_stack", release_id),
                    slots=_optional_str_list(raw_item.get("slots"), "item slots", release_id),
                    prototype=None,
                    source="generated-official-metadata",
                    # Existing generated catalogs predate S2 resource metadata;
                    # absent fields deliberately keep their old None/default behavior.
                    unit_weight=_optional_float(
                        raw_item.get("unit_weight"),
                        "item unit_weight",
                        release_id,
                    ),
                    serialization_family=_optional_str(
                        raw_item.get("serialization_family"),
                        "item serialization_family",
                        release_id,
                    ),
                    icon_x=_optional_int(raw_item.get("icon_x"), "item icon_x", release_id),
                    icon_y=_optional_int(raw_item.get("icon_y"), "item icon_y", release_id),
                    icon_texture=_optional_str(
                        raw_item.get("icon_texture"),
                        "item icon_texture",
                        release_id,
                    ),
                )
            )
        items = catalog_from_items(release_id, definitions, source_root=source_root)

        factions: FactionCatalog | None = None
        raw_factions = raw_release.get("factions")
        if raw_factions is not None:
            if not isinstance(raw_factions, list):
                raise CatalogBundleError(f"Browser catalog: invalid factions for {release_id!r}")
            faction_definitions: list[FactionDefinition] = []
            for raw_faction in raw_factions:
                if not isinstance(raw_faction, Mapping) or not isinstance(
                    raw_faction.get("key"), str
                ):
                    raise CatalogBundleError(
                        f"Browser catalog: invalid faction for {release_id!r}"
                    )
                faction_key = raw_faction["key"]
                assert isinstance(faction_key, str)
                faction_release_id = raw_faction.get("release_id", release_id)
                if faction_release_id != release_id:
                    raise CatalogBundleError(
                        f"Browser catalog: foreign faction release for {release_id!r}"
                    )
                source = raw_faction.get("source")
                if not isinstance(source, str):
                    raise CatalogBundleError(
                        f"Browser catalog: invalid faction source for {release_id!r}"
                    )
                faction_definitions.append(
                    FactionDefinition(
                        key=faction_key,
                        display_name=_optional_str(
                            raw_faction.get("display_name"),
                            "faction display_name",
                            release_id,
                        ),
                        numeric_id=_optional_int(
                            raw_faction.get("numeric_id"),
                            "faction numeric_id",
                            release_id,
                        ),
                        source=source,
                        release_id=release_id,
                    )
                )

            raw_relations = raw_release.get("relation_addresses", [])
            if not isinstance(raw_relations, list):
                raise CatalogBundleError(
                    f"Browser catalog: invalid relation_addresses for {release_id!r}"
                )
            relations: list[tuple[str, str, int]] = []
            for raw_relation in raw_relations:
                if not isinstance(raw_relation, Mapping):
                    raise CatalogBundleError(
                        f"Browser catalog: invalid faction relation for {release_id!r}"
                    )
                source_key = raw_relation.get("source")
                target_key = raw_relation.get("target")
                value = raw_relation.get("value")
                if (
                    not isinstance(source_key, str)
                    or not isinstance(target_key, str)
                    or not isinstance(value, int)
                    or isinstance(value, bool)
                ):
                    raise CatalogBundleError(
                        f"Browser catalog: invalid faction relation for {release_id!r}"
                    )
                for field in ("row", "column"):
                    _optional_int(raw_relation.get(field), f"relation {field}", release_id)
                relations.append((source_key, target_key, value))

            numeric_fields = {
                field: _optional_int(raw_release.get(field), field, release_id)
                for field in (
                    "goodwill_min",
                    "goodwill_max",
                    "attitude_neutral_threshold",
                    "attitude_friend_threshold",
                )
            }
            factions = FactionCatalog(
                release_id=release_id,
                source_root=source_root,
                factions=tuple(faction_definitions),
                relations=tuple(relations),
                goodwill_min=numeric_fields["goodwill_min"],
                goodwill_max=numeric_fields["goodwill_max"],
                attitude_neutral_threshold=numeric_fields["attitude_neutral_threshold"],
                attitude_friend_threshold=numeric_fields["attitude_friend_threshold"],
            )

        upgrades: UpgradeCatalog | None = None
        raw_upgrades = raw_release.get("upgrades")
        if raw_upgrades is not None:
            if not isinstance(raw_upgrades, list):
                raise CatalogBundleError(f"Browser catalog: invalid upgrades for {release_id!r}")
            upgrade_definitions: list[UpgradeDefinition] = []
            for raw_upgrade in raw_upgrades:
                if not isinstance(raw_upgrade, Mapping) or not isinstance(
                    raw_upgrade.get("key"), str
                ):
                    raise CatalogBundleError(
                        f"Browser catalog: invalid upgrade for {release_id!r}"
                    )
                upgrade_key = raw_upgrade["key"]
                assert isinstance(upgrade_key, str)
                upgrade_release_id = raw_upgrade.get("release_id", release_id)
                if upgrade_release_id != release_id:
                    raise CatalogBundleError(
                        f"Browser catalog: foreign upgrade release for {release_id!r}"
                    )
                source = raw_upgrade.get("source")
                if not isinstance(source, str):
                    raise CatalogBundleError(
                        f"Browser catalog: invalid upgrade source for {release_id!r}"
                    )
                applicable = raw_upgrade.get("applicable_item_keys", [])
                if not isinstance(applicable, list) or not all(
                    isinstance(value, str) for value in applicable
                ):
                    raise CatalogBundleError(
                        f"Browser catalog: invalid upgrade item binding for {release_id!r}"
                    )
                upgrade_definitions.append(
                    UpgradeDefinition(
                        key=upgrade_key,
                        display_name=_optional_str(
                            raw_upgrade.get("display_name"),
                            "upgrade display_name",
                            release_id,
                        ),
                        category=_optional_str(
                            raw_upgrade.get("category"),
                            "upgrade category",
                            release_id,
                        ),
                        item_key=_optional_str(
                            raw_upgrade.get("item_key"),
                            "upgrade item_key",
                            release_id,
                        ),
                        source=source,
                        release_id=release_id,
                        section=_optional_str(
                            raw_upgrade.get("section"),
                            "upgrade section",
                            release_id,
                        ),
                        property_name=_optional_str(
                            raw_upgrade.get("property"),
                            "upgrade property",
                            release_id,
                        ),
                        icon=_optional_str(raw_upgrade.get("icon"), "upgrade icon", release_id),
                        applicable_item_keys=tuple(applicable),
                    )
                )
            upgrades = UpgradeCatalog(release_id, source_root, tuple(upgrade_definitions))

        loaded[release_id] = CatalogBundle(release_id, items, factions, upgrades)
    return _borrow_series_names(loaded)


_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
# Firearms, suits and helmets carry different names between the three games
# (Clear Sky's ``wpn_val`` is «Лавина», not the Call of Pripyat name), so they
# never borrow.  Artifacts, rounds, food, medicine and devices do not change.
_NO_BORROW_PREFIXES = ("wpn_", "helm_", "mp_")
_NO_BORROW_FAMILIES = ("weapon", "outfit")
# Community keys whose meaning differs per game (the player's own faction).
_NO_BORROW_FACTIONS = frozenset({"actor"})


def _is_russian(name: str | None) -> bool:
    return bool(name and _CYRILLIC_RE.search(name))


def _donor_item_name(donors: list[CatalogBundle], key: str) -> str | None:
    for donor in donors:
        definition = donor.items.resolve(key)
        if definition is not None and _is_russian(definition.display_name):
            return definition.display_name
    return None


def _borrow_series_names(loaded: dict[str, CatalogBundle]) -> dict[str, CatalogBundle]:
    """Fill a missing/English X-Ray name from a sibling game's Russian name.

    The Call of Pripyat snapshot was generated from an English install and
    lacks most names.  The editor UI is Russian, so identical keys that keep
    their meaning across the trilogy reuse the Russian label.  Presentation
    only: keys, serializer metadata and write capabilities are untouched.
    """

    xray = [
        release_id
        for release_id in loaded
        if release_by_id(release_id).family != "stalker2"
    ]
    for release_id in xray:
        bundle = loaded[release_id]
        donors = [loaded[other] for other in xray if other != release_id]

        items = []
        for item in bundle.items.items:
            family = (item.serialization_family or "").casefold()
            borrow = (
                not _is_russian(item.display_name)
                and not item.key.casefold().startswith(_NO_BORROW_PREFIXES)
                and not item.key.casefold().endswith("_outfit")
                and not family.startswith(_NO_BORROW_FAMILIES)
            )
            name = _donor_item_name(donors, item.key) if borrow else None
            items.append(replace(item, display_name=name) if name else item)
        factions = bundle.factions
        if factions is not None:
            borrowed = []
            for faction in factions.factions:
                name = None
                if (
                    not _is_russian(faction.display_name)
                    and faction.key not in _NO_BORROW_FACTIONS
                ):
                    for donor in donors:
                        if donor.factions is None:
                            continue
                        match = next(
                            (
                                candidate
                                for candidate in donor.factions.factions
                                if candidate.key == faction.key
                                and _is_russian(candidate.display_name)
                            ),
                            None,
                        )
                        if match is not None:
                            name = match.display_name
                            break
                borrowed.append(replace(faction, display_name=name) if name else faction)
            factions = replace(factions, factions=tuple(borrowed))
        loaded[release_id] = CatalogBundle(
            release_id,
            replace(bundle.items, items=tuple(items)),
            factions,
            bundle.upgrades,
        )
    return loaded


def load_catalog_file(path: Path, *, source_root: Path | None = None) -> dict[str, CatalogBundle]:
    """Read one generated catalog file without exposing its path in entries."""

    try:
        payload = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CatalogBundleError(f"Не удалось прочитать browser catalog: {path}") from exc
    return load_catalog_payload(payload, source_root=source_root)


__all__ = [
    "CatalogBundle",
    "CatalogBundleError",
    "load_catalog_file",
    "load_catalog_payload",
]
