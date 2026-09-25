"""One place that turns a parsed inventory row into the name players know.

Trilogy rows resolve through the official catalog (Russian source names,
translated by :func:`editor.i18n.tr_item`); S.T.A.L.K.E.R. 2 rows keep their
raw save-local SID in ``display_name`` and are labelled by
:func:`editor.s2_names.s2_readable_name`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .i18n import tr_item
from .s2_names import s2_readable_name

if TYPE_CHECKING:
    from save_format import InventoryItem

    from .catalog import ItemCatalog, ItemDefinition


def catalog_definition(catalog: ItemCatalog | None, item: InventoryItem) -> ItemDefinition | None:
    if catalog is None:
        return None
    definition = catalog.resolve(item.type_key)
    if definition is None and item.display_name:
        definition = catalog.resolve_key_or_display_name(item.display_name)
    return definition


def item_label(item: InventoryItem, catalog: ItemCatalog | None = None, *, stalker2: bool | None = None) -> str | None:
    definition = catalog_definition(catalog, item)
    if definition is not None and definition.display_name and not definition.display_name.casefold().startswith("st_"):
        return tr_item(definition.display_name)
    s2 = stalker2 if stalker2 is not None else _looks_like_s2(item)
    if s2:
        return s2_readable_name(item.display_name, kind_code=item.kind_code)
    return item.display_name


def module_label(sid: str, catalog: ItemCatalog | None = None, *, stalker2: bool = False) -> str:
    """Readable name for a module, attachment or upgrade identifier."""

    if catalog is not None:
        definition = catalog.resolve(sid)
        if definition is not None and definition.display_name:
            return tr_item(definition.display_name) or sid
    if stalker2:
        return s2_readable_name(sid) or sid
    return sid


def _looks_like_s2(item: InventoryItem) -> bool:
    # S2 compact keys are exactly three hex bytes; X-Ray keys are sections.
    key = item.type_key or ""
    return len(key) == 6 and all(ch in "0123456789abcdef" for ch in key.casefold())


__all__ = ["catalog_definition", "item_label", "module_label"]
