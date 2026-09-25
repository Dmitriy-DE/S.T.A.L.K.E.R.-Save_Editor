"""Python side of the browser build.

This module is the only web-specific Python in the project. It installs the
WASM decoder needed by the compressed-save path and turns the same
multi-format registry results the desktop app uses into plain dictionaries the
page can render. Any editing rule that lived here would be a second
implementation, which is exactly what this build avoids.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import editor.codec as codec
import save_format as sf
from editor import official_names
from editor.catalog import FactionCatalog, GameCatalog, ItemCatalog, UpgradeCatalog
from editor.catalog_bundle import CatalogBundleError, load_catalog_payload
from editor.equipment import category_label, equipment_items, helmet_category_supported
from editor.formats import detect_or_raise
from editor.i18n import tr
from editor.item_names import item_label
from editor.models import EditPlan, SourceRef
from editor.xray_save import XRAY_FORMATS, catalog_from_save_inventory


def _to_js_bytes(payload: bytes) -> Any:
    """Hand a real Uint8Array to JavaScript.

    Pyodide does not implicitly convert Python buffers: a ``bytes`` passed to a
    JS function arrives as a PyProxy, and the WASM decoder then fails with a
    bare "Failed to decode".  The conversion has to be explicit.
    """

    try:
        from pyodide.ffi import to_js
    except ImportError:  # not running under Pyodide
        return payload
    return to_js(payload)


def _optional_int(value: Any) -> int | None:
    """Normalize Python ``None`` and Pyodide's JavaScript ``null`` proxy."""

    if value is None or type(value).__name__ in {"JsNull", "JsUndefined"}:
        return None
    return int(value)


class _WasmDecoder:
    """Adapter over the page's ooz-wasm binding."""

    def __init__(self, call: Any) -> None:
        self._call = call

    def decompress(self, stream: bytes, unpacked_size: int) -> bytes:
        result = self._call(_to_js_bytes(bytes(stream)), unpacked_size)
        # The binding returns a JS Uint8Array; to_py() gives a bytes-like view.
        to_py = getattr(result, "to_py", None)
        return bytes(to_py() if callable(to_py) else result)


def install_decoder(call: Any) -> None:
    codec.register_decoder(_WasmDecoder(call))


def _human_size(size: int) -> str:
    if size < 1024:
        return tr("{0} Б", size)
    if size < 1024 * 1024:
        return tr("{0:.1f} КБ", size / 1024)
    return tr("{0:.2f} МБ", size / (1024 * 1024))


def _metadata_rows(
    info: sf.SaveInfo,
    name: str,
    size: int,
    *,
    money_editable: bool,
) -> list[list[str]]:
    money = tr("неизвестно") if info.money is None else str(info.money)
    money_status = (
        tr("редактируется")
        if money_editable
        else f"read-only (anchor × {info.money_anchor_count})"
    )
    parsed = len({item.handle for item in info.inventory})
    rows = [
        [tr("Файл"), name, _human_size(size)],
        ([
            "CRC-32",
            f"{info.stored_crc32:08X}",
            "PASS" if info.crc_ok else tr("FAIL (вычислено {0:08X})", info.computed_crc32),
        ] if info.crc_present else [
            tr("Целостность"),
            info.integrity_name,
            tr("проверен контейнер и LZO payload"),
        ]),
        ["SHA-256", info.sha256, tr("исходный снимок")],
        [
            tr("Размер контейнера"),
            f"{_human_size(info.packed_size)} → {_human_size(info.unpacked_size)}",
            tr("Kraken распакован") if info.crc_present else tr("LZO1X распакован"),
        ],
        [tr("Баланс купонов"), money, money_status],
        ["Owned handles", str(len(info.owned_handles)), tr("прочитано")],
        [
            "Grid handles" if info.crc_present else "Actor inventory objects",
            f"{parsed} / {info.grid_handle_count}",
            tr("разобрано / объявлено") if info.crc_present else tr("прочитано по parent actor"),
        ],
        [
            "Grid cells",
            str(info.grid_cell_count),
            tr("прочитано") if info.crc_present else tr("в X-Ray не используется"),
        ],
        [tr("Объекты инвентаря"), str(len(info.inventory)), tr("в сетке") if info.crc_present else tr("в actor registry")],
        ["Orphan handles", str(len(info.orphans)), tr("вне сетки")],
        [
            "Unresolved handles",
            str(len(info.unresolved_handles)),
            "read-only" if info.unresolved_handles else tr("нет"),
        ],
    ]
    if info.crc_present:
        rows.append(["UE5 GVAS schema", tr("не разобрана"), tr("контейнер валиден, схема не подтверждена")])
    else:
        rows.extend(
            [
                ["X-Ray outer version", str(info.container_version), tr("подтверждён")],
                ["Actor spawn version", str(info.format_version), tr("подтверждён")],
                [tr("Время игры"), tr("неизвестно") if info.game_time is None else str(info.game_time), tr("прочитано")],
                [tr("Уровень"), info.level_name or tr("неизвестно"), tr("прочитано из SPAWN") if info.level_name else tr("не найден")],
            ]
        )
    return rows


def _catalog_icon_fields(
    catalog: ItemCatalog | None,
    item_key: str,
) -> dict[str, int | str | None]:
    """Return official atlas metadata without turning an unknown key into a guess."""

    definition = catalog.resolve(item_key) if catalog is not None else None
    if definition is None:
        return {"icon_x": None, "icon_y": None, "icon_texture": None}
    return {
        "icon_x": definition.icon_x,
        "icon_y": definition.icon_y,
        "icon_texture": definition.icon_texture,
    }


_state: dict[str, Any] = {}
_catalogs: dict[str, ItemCatalog] = {}
_faction_catalogs: dict[str, FactionCatalog] = {}
_upgrade_catalogs: dict[str, UpgradeCatalog] = {}


def install_catalogs(payload: str) -> None:
    """Install generated official metadata supplied by the browser shell."""

    try:
        bundles = load_catalog_payload(payload)
    except CatalogBundleError as exc:
        raise sf.SaveError(str(exc)) from exc
    _catalogs.clear()
    _catalogs.update({release_id: bundle.items for release_id, bundle in bundles.items()})
    _faction_catalogs.clear()
    _faction_catalogs.update(
        {
            release_id: bundle.factions
            for release_id, bundle in bundles.items()
            if bundle.factions is not None
        }
    )
    _upgrade_catalogs.clear()
    _upgrade_catalogs.update(
        {
            release_id: bundle.upgrades
            for release_id, bundle in bundles.items()
            if bundle.upgrades is not None
        }
    )

def _item_name(
    catalog: ItemCatalog | None, item: sf.InventoryItem, release_id: str | None = None
) -> str:
    """The same official/catalog name the desktop table shows."""

    return item_label(item, catalog, release_id=release_id) or tr("Неизвестный объект")


def install_official_names(payload: str) -> int:
    """Install the Enhanced Edition name snapshot fetched by the page."""

    return official_names.install(payload)


def analyze(data: bytes, name: str) -> str:
    """Parse one save and return a JSON snapshot for the page."""

    payload = bytes(data)
    format_ = detect_or_raise(payload, display_name=name)
    info = format_.inspect(payload)
    _state["data"] = payload
    _state["sha256"] = hashlib.sha256(payload).hexdigest()
    _state["name"] = name
    _state["format"] = format_
    _state.pop("output", None)
    catalog = _catalogs.get(format_.id)
    catalog_source: str | None = None
    spec = getattr(format_, "spec", None)
    if (
        catalog is None
        and format_.id in {candidate.id for candidate in XRAY_FORMATS}
        and spec is not None
    ):
        # Keep the fallback for Python bridge tests and diagnostics, but the
        # published page installs generated official metadata before opening a
        # file.  It is intentionally marked as save-observed below.
        catalog = catalog_from_save_inventory(spec, info.inventory)
        catalog_source = "save-observed"
    else:
        catalog_source = "generated-official" if catalog is not None else None
    _state["catalog"] = catalog
    faction_catalog = _faction_catalogs.get(format_.id)
    _state["faction_catalog"] = faction_catalog
    upgrade_catalog = _upgrade_catalogs.get(format_.id)
    _state["upgrade_catalog"] = upgrade_catalog
    relation_values = dict(info.faction_relations)
    equipment_rows = equipment_items(
        info.inventory,
        release_id=format_.release_id,
        catalog=catalog,
    )
    equipment_by_handle = {row.handle: row for row in equipment_rows}

    return json.dumps(
        {
            "name": name,
            "size": len(payload),
            "size_text": _human_size(len(payload)),
            "format_id": format_.id,
            "format_title": format_.title,
            "release_id": format_.release_id,
            "edition": format_.edition,
            "helmet_category_supported": helmet_category_supported(format_.release_id),
            "capabilities": format_.capabilities.as_dict(),
            "catalog_available": catalog is not None and bool(catalog.items),
            "catalog_source": catalog_source,
            "catalog_items": [
                {
                    "key": item.key,
                    "name": official_names.official_name(format_.release_id, "items", item.key)
                    or item.display_name
                    or item.key,
                    "category": item.category,
                    "max_stack": item.max_stack,
                    "serialization_family": item.serialization_family,
                    "icon_x": item.icon_x,
                    "icon_y": item.icon_y,
                    "icon_texture": item.icon_texture,
                }
                for item in (catalog.items if catalog is not None else ())
            ],
            "faction_catalog_available": faction_catalog is not None
            and bool(faction_catalog.factions),
            "catalog_factions": [
                {
                    "key": faction.key,
                    "name": official_names.official_name(format_.release_id, "factions", faction.key)
                    or faction.display_name
                    or faction.key,
                    "numeric_id": faction.numeric_id,
                }
                for faction in (
                    faction_catalog.factions if faction_catalog is not None else ()
                )
            ],
            "upgrade_catalog_available": (
                format_.capabilities.edit_upgrades
                and upgrade_catalog is not None
                and bool(upgrade_catalog.upgrades)
            ),
            "catalog_upgrades": [
                {
                    "key": upgrade.key,
                    "name": official_names.official_name(format_.release_id, "upgrades", upgrade.key)
                    or upgrade.display_name
                    or upgrade.key,
                    "category": upgrade.category,
                    "item_key": upgrade.item_key,
                    "applicable_item_keys": list(upgrade.applicable_item_keys),
                    "section": upgrade.section,
                    "property_name": upgrade.property_name,
                    "icon": upgrade.icon,
                }
                for upgrade in (
                    upgrade_catalog.upgrades if upgrade_catalog is not None else ()
                )
            ],
            "faction_goodwill_min": (
                faction_catalog.goodwill_min if faction_catalog is not None else None
            ),
            "faction_goodwill_max": (
                faction_catalog.goodwill_max if faction_catalog is not None else None
            ),
            "faction_relations_editable": info.faction_relations_editable,
            "player_faction_index": info.player_faction_index,
            "player_faction_editable": (
                format_.capabilities.edit_player_faction
                and info.player_faction_editable
            ),
            "faction_relations": [
                {
                    "key": faction.key,
                    "name": faction.display_name or faction.key,
                    "numeric_id": faction.numeric_id,
                    "value": relation_values.get(faction.numeric_id, 0),
                    "stored": faction.numeric_id in relation_values,
                }
                for faction in (
                    faction_catalog.factions if faction_catalog is not None else ()
                )
                if faction.numeric_id is not None
            ],
            "sha256": info.sha256,
            "crc_ok": info.crc_ok,
            "crc_present": info.crc_present,
            "integrity_name": info.integrity_name,
            "format_version": info.format_version,
            "container_version": info.container_version,
            "game_time": info.game_time,
            "level_name": info.level_name,
            "money": info.money,
            "money_editable": (
                format_.capabilities.edit_money
                and info.money is not None
                and info.money_anchor_count == 1
            ),
            "inventory_count": len(info.inventory),
            "equipment_count": len(equipment_rows),
            "stack_max": 65535 if format_.id in {"stalker-soc", "stalker-cs", "stalker-cop"} else 1_000_000,
            "warnings": list(info.warnings),
            "metadata": _metadata_rows(
                info,
                name,
                len(payload),
                money_editable=(
                    format_.capabilities.edit_money
                    and info.money is not None
                    and info.money_anchor_count == 1
                ),
            ),
            "inventory": [
                {
                    "handle": item.handle,
                    "handle_hex": item.handle_hex,
                    "category": item.category,
                    "product_category": (
                        equipment_by_handle[item.handle].category
                        if item.handle in equipment_by_handle
                        else "other"
                    ),
                    "category_label": category_label(
                        equipment_by_handle[item.handle].category
                        if item.handle in equipment_by_handle
                        else "other"
                    ),
                    "type_key": item.type_key,
                    "position": item.position,
                    "size_text": item.size_text,
                    "count": item.count,
                    "total_weight": None if item.total_weight is None else round(item.total_weight, 3),
                    "weight_known": item.total_weight is not None,
                    "name": _item_name(catalog, item, format_.release_id),
                    "condition": item.condition,
                    "condition_editable": bool(item.condition_editable),
                    "storage": item.storage,
                    "observation_source": item.observation_source,
                    "device_subtype": (
                        equipment_by_handle[item.handle].device_subtype
                        if item.handle in equipment_by_handle
                        else None
                    ),
                    "placement_type": item.placement_type,
                    "placement_slot": item.placement_slot,
                    "placement_base_slot": item.placement_base_slot,
                    "placement_editable": bool(item.placement_editable),
                    "remove_editable": bool(
                        format_.capabilities.remove_items and item.remove_editable
                    ),
                    "remove_reason": item.remove_reason,
                    **_catalog_icon_fields(catalog, item.type_key),
                    "modules": None if item.modules is None else list(item.modules),
                    "upgrades": None if item.upgrades is None else list(item.upgrades),
                    "upgrade_editable": bool(
                        format_.capabilities.edit_upgrades
                        and item.upgrades_editable
                        and upgrade_catalog is not None
                    ),
                    "editable": bool(
                        format_.capabilities.edit_stacks and item.editable_count
                    ),
                }
                for item in info.inventory
            ],
            "equipment": [row.as_dict() for row in equipment_rows],
        },
        ensure_ascii=False,
    )


def prepare(
    money: int | None,
    stacks_json: str,
    adds_json: str = "[]",
    detach_json: str = "[]",
    durability_json: str = "[]",
    relations_json: str = "[]",
    player_faction_json: str = "null",
    upgrades_json: str = "[]",
    placements_json: str = "[]",
) -> str:
    """Apply staged edits to the analyzed bytes and keep the result in memory."""

    data = _state.get("data")
    if data is None:
        raise sf.SaveError(tr("Сначала открой сейв"))

    stacks = tuple((int(handle), int(count)) for handle, count in json.loads(stacks_json))
    adds = tuple(
        (str(entry[0]), int(entry[1]), "inventory")
        for entry in json.loads(adds_json)
    )
    detach = tuple(
        (
            int(entry[0]) if isinstance(entry, (list, tuple)) else int(entry),
            bool(entry[1]) if isinstance(entry, (list, tuple)) and len(entry) > 1 else True,
        )
        for entry in json.loads(detach_json)
    )
    durability = tuple(
        (int(entry[0]), float(entry[1]))
        for entry in json.loads(durability_json)
    )
    faction_relations = tuple(
        (str(entry[0]), int(entry[1]))
        for entry in json.loads(relations_json)
    )
    player_faction_value = json.loads(player_faction_json)
    if player_faction_value is None:
        player_faction: str | None = None
    elif isinstance(player_faction_value, str):
        player_faction = player_faction_value
    else:
        raise sf.SaveError(tr("Внутренняя ошибка: неверная группировка игрока"))
    upgrades = tuple(
        (int(entry[0]), tuple(str(value) for value in entry[1]))
        for entry in json.loads(upgrades_json)
    )
    placements = tuple(
        (
            int(entry[0]),
            str(entry[1]),
            None if entry[2] is None else int(entry[2]),
        )
        for entry in json.loads(placements_json)
    )
    normalized_money = _optional_int(money)
    plan = EditPlan(
        source=SourceRef(
            kind="local",
            locator=str(_state.get("name") or "save.sav"),
            sha256=str(_state["sha256"]),
        ),
        money=normalized_money,
        stacks=stacks,
        adds=adds,
        detach=detach,
        durability=durability,
        faction_relations=faction_relations,
        player_faction=player_faction,
        upgrades=upgrades,
        placements=placements,
    )
    format_ = _state.get("format")
    if format_ is None:
        format_ = detect_or_raise(data, display_name=str(_state.get("name") or "save"))
    if normalized_money is not None and not format_.capabilities.edit_money:
        raise sf.SaveError(
            tr("{0}: запись пока недоступна — формат ещё не подтверждён загрузкой в игре", format_.release_id)
        )
    if stacks and not format_.capabilities.edit_stacks:
        raise sf.SaveError(
            tr("{0}: изменение количества ещё не подтверждено проверкой в игре", format_.release_id)
        )
    if adds and not format_.capabilities.add_items:
        raise sf.SaveError(
            tr("{0}: добавление предметов ещё не подтверждено проверкой в игре", format_.release_id)
        )
    if detach and not format_.capabilities.remove_items:
        raise sf.SaveError(
            tr("{0}: удаление предметов ещё не подтверждено проверкой в игре", format_.release_id)
        )
    if durability and not format_.capabilities.edit_durability:
        raise sf.SaveError(
            tr("{0}: изменение прочности ещё не подтверждено проверкой в игре", format_.release_id)
        )
    if faction_relations and not format_.capabilities.edit_relations:
        raise sf.SaveError(
            tr("{0}: изменение отношений ещё не подтверждено проверкой в игре", format_.release_id)
        )
    if player_faction is not None and not format_.capabilities.edit_player_faction:
        raise sf.SaveError(
            tr("{0}: смена группировки игрока ещё не подтверждена проверкой в игре", format_.release_id)
        )
    if upgrades and not format_.capabilities.edit_upgrades:
        raise sf.SaveError(
            tr("{0}: изменение улучшений ещё не подтверждено проверкой в игре", format_.release_id)
        )
    if placements and not format_.capabilities.edit_placement:
        raise sf.SaveError(
            tr("{0}: изменение размещения ещё не подтверждено проверкой в игре", format_.release_id)
        )
    item_catalog = _state.get("catalog")
    faction_catalog = _state.get("faction_catalog")
    upgrade_catalog = _state.get("upgrade_catalog")
    if not isinstance(faction_catalog, FactionCatalog):
        faction_catalog = FactionCatalog(format_.release_id, None, ())
    game_catalog = (
        GameCatalog(format_.release_id, item_catalog, faction_catalog, upgrade_catalog)
        if isinstance(item_catalog, ItemCatalog)
        and (
            isinstance(_state.get("faction_catalog"), FactionCatalog)
            or isinstance(upgrade_catalog, UpgradeCatalog)
        )
        else None
    )
    prepared = format_.prepare(
        data,
        plan,
        source_name=str(_state.get("name") or "save.sav"),
        catalog=item_catalog if isinstance(item_catalog, ItemCatalog) else None,
        game_catalog=game_catalog,
    )
    _state["output"] = prepared.data

    before = format_.inspect(data)
    after = format_.inspect(prepared.data)
    before_counts = {item.handle: item.count for item in before.inventory}
    after_counts = {item.handle: item.count for item in after.inventory}
    before_handles = {item.handle for item in before.inventory}
    added_items = [
        [item.handle_hex, item.type_key, item.count]
        for item in after.inventory
        if item.handle not in before_handles
    ]
    removed_handles = [
        f"0x{handle:08X}"
        for handle, _deep in detach
        if handle not in {item.handle for item in after.inventory}
    ]
    before_conditions = {item.handle: item.condition for item in before.inventory}
    after_conditions = {item.handle: item.condition for item in after.inventory}
    before_relations = dict(before.faction_relations)
    after_relations = dict(after.faction_relations)
    before_player_faction = before.player_faction_index
    after_player_faction = after.player_faction_index
    before_upgrades = {item.handle: item.upgrades for item in before.inventory}
    after_upgrades = {item.handle: item.upgrades for item in after.inventory}
    before_placements = {
        item.handle: (item.placement_type, item.placement_slot)
        for item in before.inventory
    }
    after_placements = {
        item.handle: (item.placement_type, item.placement_slot)
        for item in after.inventory
    }
    faction_catalog = _state.get("faction_catalog")
    faction_ids = {
        faction.key: faction.numeric_id
        for faction in (faction_catalog.factions if isinstance(faction_catalog, FactionCatalog) else ())
    }
    return json.dumps(
        {
            "output_sha256": prepared.output_sha256,
            "size": len(prepared.data),
            "size_text": _human_size(len(prepared.data)),
            "money": [before.money, after.money],
            "stacks": [
                [f"0x{handle:08X}", before_counts.get(handle), after_counts.get(handle)]
                for handle, _ in stacks
            ],
            "adds": added_items,
            "removed": removed_handles,
            "durability": [
                [
                    f"0x{handle:08X}",
                    before_conditions.get(handle),
                    after_conditions.get(handle),
                ]
                for handle, _condition in durability
            ],
            "faction_relations": [
                [
                    key,
                    before_relations.get(faction_ids.get(key)),
                    after_relations.get(faction_ids.get(key)),
                ]
                for key, _goodwill in faction_relations
            ],
            "player_faction": [before_player_faction, after_player_faction],
            "upgrades": [
                [
                    f"0x{handle:08X}",
                    None if before_upgrades.get(handle) is None else list(before_upgrades[handle] or ()),
                    None if after_upgrades.get(handle) is None else list(after_upgrades[handle] or ()),
                ]
                for handle, _values in upgrades
            ],
            "placements": [
                [
                    f"0x{handle:08X}",
                    list(before_placements.get(handle, (None, None))),
                    list(after_placements.get(handle, (None, None))),
                ]
                for handle, _placement_type, _slot_id in placements
            ],
            "source_unchanged": hashlib.sha256(data).hexdigest() == _state["sha256"],
        },
        ensure_ascii=False,
    )


def output_bytes() -> bytes:
    data = _state.get("output")
    if data is None:
        raise sf.SaveError(tr("Нет подготовленной копии"))
    return bytes(data)
