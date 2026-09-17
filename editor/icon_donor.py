"""Borrow inventory icons from another installed trilogy game.

Shadow of Chornobyl, Clear Sky and Call of Pripyat ship the same base item
art (weapons, ammo, food, medical items, base artifacts) under the same item
keys.  When a save's own game files are not installed locally the editor has
no atlas to crop, so every item falls back to a drawn category glyph.

This module finds another *installed* official trilogy release whose icon
atlas is actually readable and returns its :class:`ItemCatalog`.  The icon
resolver then looks items up in that donor catalog by key, using the donor's
own atlas coordinates, so shared items render with real game art.  Nothing is
copied or bundled: the atlas is read from the local install on demand, exactly
like the primary path.
"""

from __future__ import annotations

from editor.catalog import ItemCatalog
from editor.platforms import installed_releases
from editor.releases import release_by_id
from editor.xray_catalog import XRayCatalogProvider


def discover_icon_donor_catalog(
    *,
    prefer_not: str | None = None,
    **discovery_kwargs: object,
) -> ItemCatalog | None:
    """Return an installed trilogy catalog whose atlas can supply icons.

    ``prefer_not`` is the release id of the opened save; a donor from a
    *different* release is preferred so we never pretend the save's own game
    is installed, but any readable trilogy atlas is accepted.  Extra keyword
    arguments are forwarded to :func:`installed_releases` (used by tests to
    inject a synthetic Steam layout).
    """

    candidates: list[ItemCatalog] = []
    for game in installed_releases(**discovery_kwargs):  # type: ignore[arg-type]
        try:
            release = release_by_id(game.release_id)
        except KeyError:
            continue
        try:
            catalog = XRayCatalogProvider().load(release, game.install_dir)
        except (OSError, ValueError):
            catalog = None
        if catalog is None or catalog.source_root is None:
            continue
        if not any(definition.icon_x is not None for definition in catalog.items):
            continue
        candidates.append(catalog)

    if not candidates:
        return None
    if prefer_not is not None:
        for catalog in candidates:
            if catalog.release_id != prefer_not:
                return catalog
    return candidates[0]
