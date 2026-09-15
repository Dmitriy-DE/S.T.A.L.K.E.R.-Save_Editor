"""Resource-backed X-Ray community/faction catalog extraction.

The engine calls these identifiers ``communities``.  The catalog keeps the
engine spelling exactly as it appears in ``game_relations.ltx`` because that
same key is used by ``character_community()`` and by the string table.  No
cross-game list is kept here: every result comes from the selected release's
resource sections.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .catalog import FactionCatalog, FactionDefinition


def _int_value(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip(), 0)
    except ValueError:
        try:
            return int(float(value.strip().replace(",", ".")))
        except ValueError:
            return None


def _community_pairs(value: str | None) -> tuple[tuple[str, int], ...]:
    if not value:
        return ()
    tokens = tuple(token.strip() for token in value.split(",") if token.strip())
    if len(tokens) < 2 or len(tokens) % 2:
        return ()
    pairs: list[tuple[str, int]] = []
    for index in range(0, len(tokens), 2):
        key = tokens[index]
        numeric_id = _int_value(tokens[index + 1])
        if not key or numeric_id is None:
            return ()
        pairs.append((key, numeric_id))
    return tuple(pairs)


def _relation_values(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    values: list[int] = []
    for token in value.split(","):
        parsed = _int_value(token)
        if parsed is None:
            return ()
        values.append(parsed)
    return tuple(values)


def factions_from_sections(
    sections: Iterable[tuple[str, Any, Mapping[str, str]]],
    localization: Mapping[str, str],
    *,
    release_id: str,
    source_prefix: str = "",
    source_root: Path | None = None,
) -> FactionCatalog | None:
    """Build one faction catalog from resolved official LTX sections.

    ``sections`` has the same resolved-section shape used by the item reader:
    ``(section name, section object, inherited values)``.  Keeping this
    function independent of the filesystem/archive reader makes it usable for
    both unpacked resources and verified X-Ray archives.
    """

    communities: tuple[tuple[str, int], ...] = ()
    community_source = ""
    relation_rows: Mapping[str, str] = {}
    game_relations_values: Mapping[str, str] = {}
    action_points_values: Mapping[str, str] = {}
    for name, section, values in sections:
        lowered = name.casefold()
        if lowered == "game_relations":
            if not communities:
                parsed = _community_pairs(values.get("communities"))
                if parsed:
                    communities = parsed
                    community_source = f"{source_prefix}{getattr(section, 'source', '')}#communities"
            if not game_relations_values:
                game_relations_values = values
        elif lowered == "communities_relations" and not relation_rows:
            relation_rows = values
        elif lowered == "action_points" and not action_points_values:
            action_points_values = values

    if not communities:
        return None

    keys = tuple(key for key, _ in communities)
    source = community_source or "resource:game_relations#communities"
    factions = tuple(
        FactionDefinition(
            key=key,
            # X-Ray's UI translates CharacterInfo().Community().id() directly.
            # Missing language entries stay None instead of becoming guessed
            # English names or the key itself.
            display_name=localization.get(key),
            source=source,
            release_id=release_id,
            numeric_id=numeric_id,
        )
        for key, numeric_id in communities
    )

    relations: list[tuple[str, str, int]] = []
    for source_key in keys:
        row = _relation_values(relation_rows.get(source_key))
        if not row:
            continue
        for target_key, value in zip(keys, row, strict=False):
            relations.append((source_key, target_key, value))

    goodwill_limits = _relation_values(
        action_points_values.get("community_goodwill_limits")
    )
    return FactionCatalog(
        release_id=release_id,
        source_root=source_root,
        factions=factions,
        relations=tuple(relations),
        goodwill_min=goodwill_limits[0] if len(goodwill_limits) >= 2 else None,
        goodwill_max=goodwill_limits[1] if len(goodwill_limits) >= 2 else None,
        attitude_neutral_threshold=_int_value(
            game_relations_values.get("attitude_neutal_threshold")
        ),
        attitude_friend_threshold=_int_value(
            game_relations_values.get("attitude_friend_threshold")
        ),
    )


__all__ = ["factions_from_sections"]
