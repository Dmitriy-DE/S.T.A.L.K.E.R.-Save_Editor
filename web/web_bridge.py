"""Python side of the browser build.

This module is the only web-specific Python in the project.  It installs the
WASM decoder needed by the S.T.A.L.K.E.R. 2 path and turns the same multi-format
registry results the desktop app uses into plain dictionaries the page can
render.  Any editing rule that lived here would be a second implementation,
which is exactly what this build avoids.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import editor.codec as codec
import save_format as sf
from editor.catalog import ItemCatalog, ItemDefinition, catalog_from_items
from editor.formats import detect_or_raise
from editor.models import EditPlan, SourceRef
from editor.releases import release_by_id
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
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


def _metadata_rows(
    info: sf.SaveInfo,
    name: str,
    size: int,
    *,
    money_editable: bool,
) -> list[list[str]]:
    money = "неизвестно" if info.money is None else str(info.money)
    money_status = (
        "редактируется"
        if money_editable
        else f"read-only (anchor × {info.money_anchor_count})"
    )
    parsed = len({item.handle for item in info.inventory})
    rows = [
        ["Файл", name, _human_size(size)],
        ([
            "CRC-32",
            f"{info.stored_crc32:08X}",
            "PASS" if info.crc_ok else f"FAIL (вычислено {info.computed_crc32:08X})",
        ] if info.crc_present else [
            "Целостность",
            info.integrity_name,
            "проверен контейнер и LZO payload",
        ]),
        ["SHA-256", info.sha256, "исходный снимок"],
        [
            "Размер контейнера",
            f"{_human_size(info.packed_size)} → {_human_size(info.unpacked_size)}",
            "Kraken распакован" if info.crc_present else "LZO1X распакован",
        ],
        ["Баланс купонов", money, money_status],
        ["Owned handles", str(len(info.owned_handles)), "прочитано"],
        [
            "Grid handles" if info.crc_present else "Actor inventory objects",
            f"{parsed} / {info.grid_handle_count}",
            "разобрано / объявлено" if info.crc_present else "прочитано по parent actor",
        ],
        [
            "Grid cells",
            str(info.grid_cell_count),
            "прочитано" if info.crc_present else "в X-Ray не используется",
        ],
        ["Объекты инвентаря", str(len(info.inventory)), "в сетке" if info.crc_present else "в actor registry"],
        ["Orphan handles", str(len(info.orphans)), "вне сетки"],
        [
            "Unresolved handles",
            str(len(info.unresolved_handles)),
            "read-only" if info.unresolved_handles else "нет",
        ],
    ]
    if info.crc_present:
        rows.append(["UE5 GVAS schema", "не разобрана", "контейнер валиден, схема не подтверждена"])
    else:
        rows.extend(
            [
                ["X-Ray outer version", str(info.container_version), "подтверждён"],
                ["Actor spawn version", str(info.format_version), "подтверждён"],
                ["Время игры", "неизвестно" if info.game_time is None else str(info.game_time), "прочитано"],
                ["Уровень", info.level_name or "неизвестно", "прочитано из SPAWN" if info.level_name else "не найден"],
            ]
        )
    return rows


_state: dict[str, Any] = {}
_catalogs: dict[str, ItemCatalog] = {}


def install_catalogs(payload: str) -> None:
    """Install generated official metadata supplied by the browser shell."""

    document = json.loads(payload)
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise sf.SaveError("Некорректная версия browser catalog")
    raw_releases = document.get("releases")
    if not isinstance(raw_releases, dict):
        raise sf.SaveError("Browser catalog не содержит releases")
    loaded: dict[str, ItemCatalog] = {}
    for release_id, raw_release in raw_releases.items():
        descriptor = release_by_id(str(release_id))
        if descriptor.edition != "original":
            raise sf.SaveError(f"Browser catalog: unsupported release {release_id!r}")
        if not isinstance(raw_release, dict) or not isinstance(raw_release.get("items"), list):
            raise sf.SaveError(f"Browser catalog: invalid items for {release_id!r}")
        definitions: list[ItemDefinition] = []
        for raw_item in raw_release["items"]:
            if not isinstance(raw_item, dict) or not isinstance(raw_item.get("key"), str):
                raise sf.SaveError(f"Browser catalog: invalid item for {release_id!r}")
            definitions.append(
                ItemDefinition(
                    key=raw_item["key"],
                    display_name=None,
                    category=raw_item.get("category"),
                    unit_weight=None,
                    width=None,
                    height=None,
                    max_stack=raw_item.get("max_stack"),
                    slots=(),
                    prototype=None,
                    source="generated-official-metadata",
                    serialization_family=raw_item.get("serialization_family"),
                )
            )
        loaded[str(release_id)] = catalog_from_items(str(release_id), definitions)
    _catalogs.clear()
    _catalogs.update(loaded)


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

    return json.dumps(
        {
            "name": name,
            "size": len(payload),
            "size_text": _human_size(len(payload)),
            "format_id": format_.id,
            "format_title": format_.title,
            "release_id": format_.release_id,
            "edition": format_.edition,
            "capabilities": format_.capabilities.as_dict(),
            "catalog_available": catalog is not None and bool(catalog.items),
            "catalog_source": catalog_source,
            "catalog_items": [
                {
                    "key": item.key,
                    "name": item.display_name or item.key,
                    "category": item.category,
                    "max_stack": item.max_stack,
                    "serialization_family": item.serialization_family,
                }
                for item in (catalog.items if catalog is not None else ())
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
                    "type_key": item.type_key,
                    "position": item.position,
                    "size_text": item.size_text,
                    "count": item.count,
                    "total_weight": None if item.total_weight is None else round(item.total_weight, 3),
                    "weight_known": item.total_weight is not None,
                    "name": item.display_name or "Неизвестный объект",
                    "editable": bool(
                        format_.capabilities.edit_stacks and item.editable_count
                    ),
                }
                for item in info.inventory
            ],
        },
        ensure_ascii=False,
    )


def prepare(
    money: int | None,
    stacks_json: str,
    adds_json: str = "[]",
    detach_json: str = "[]",
) -> str:
    """Apply staged edits to the analyzed bytes and keep the result in memory."""

    data = _state.get("data")
    if data is None:
        raise sf.SaveError("Сначала открой сейв")

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
    plan = EditPlan(
        source=SourceRef(
            kind="local",
            locator=str(_state.get("name") or "save.sav"),
            sha256=str(_state["sha256"]),
        ),
        money=_optional_int(money),
        stacks=stacks,
        adds=adds,
        detach=detach,
    )
    format_ = _state.get("format")
    if format_ is None:
        format_ = detect_or_raise(data, display_name=str(_state.get("name") or "save"))
    prepared = format_.prepare(
        data,
        plan,
        source_name=str(_state.get("name") or "save.sav"),
        catalog=_state.get("catalog"),
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
            "source_unchanged": hashlib.sha256(data).hexdigest() == _state["sha256"],
        },
        ensure_ascii=False,
    )


def output_bytes() -> bytes:
    data = _state.get("output")
    if data is None:
        raise sf.SaveError("Нет подготовленной копии")
    return bytes(data)
