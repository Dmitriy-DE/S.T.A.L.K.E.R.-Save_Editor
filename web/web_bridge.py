"""Python side of the browser build.

This module is the only web-specific Python in the project.  It does not parse
or edit anything: it installs the WASM decoder into ``editor.codec`` and turns
the same ``save_format`` / ``editor.prepare`` results the desktop app uses into
plain dictionaries the page can render.  Any editing rule that lived here would
be a second implementation, which is exactly what this build avoids.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import editor.codec as codec
import save_format as sf
from editor.formats import detect_or_raise
from editor.models import EditPlan, SourceRef
from editor.prepare import prepare_edit


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


def _metadata_rows(info: sf.SaveInfo, name: str, size: int) -> list[list[str]]:
    money = "неизвестно" if info.money is None else str(info.money)
    money_status = (
        "редактируется"
        if info.money is not None and info.money_anchor_count == 1
        else f"read-only (anchor × {info.money_anchor_count})"
    )
    parsed = len({item.handle for item in info.inventory})
    return [
        ["Файл", name, _human_size(size)],
        [
            "CRC-32",
            f"{info.stored_crc32:08X}",
            "PASS" if info.crc_ok else f"FAIL (вычислено {info.computed_crc32:08X})",
        ],
        ["SHA-256", info.sha256, "исходный снимок"],
        [
            "Размер контейнера",
            f"{_human_size(info.packed_size)} → {_human_size(info.unpacked_size)}",
            "Kraken распакован",
        ],
        ["Баланс купонов", money, money_status],
        ["Owned handles", str(len(info.owned_handles)), "прочитано"],
        ["Grid handles", f"{parsed} / {info.grid_handle_count}", "разобрано / объявлено"],
        ["Grid cells", str(info.grid_cell_count), "прочитано"],
        ["Объекты инвентаря", str(len(info.inventory)), "в сетке"],
        ["Orphan handles", str(len(info.orphans)), "вне сетки"],
        [
            "Unresolved handles",
            str(len(info.unresolved_handles)),
            "read-only" if info.unresolved_handles else "нет",
        ],
        ["UE5 GVAS schema", "не разобрана", "контейнер валиден, схема не подтверждена"],
    ]


_state: dict[str, Any] = {}


def analyze(data: bytes, name: str) -> str:
    """Parse one save and return a JSON snapshot for the page."""

    payload = bytes(data)
    format_ = detect_or_raise(payload, display_name=name)
    info = format_.inspect(payload)
    _state["data"] = payload
    _state["sha256"] = hashlib.sha256(payload).hexdigest()
    _state["name"] = name

    return json.dumps(
        {
            "name": name,
            "size": len(payload),
            "size_text": _human_size(len(payload)),
            "format_id": format_.id,
            "format_title": format_.title,
            "sha256": info.sha256,
            "crc_ok": info.crc_ok,
            "money": info.money,
            "money_editable": info.money is not None and info.money_anchor_count == 1,
            "inventory_count": len(info.inventory),
            "warnings": list(info.warnings),
            "metadata": _metadata_rows(info, name, len(payload)),
            "inventory": [
                {
                    "handle": item.handle,
                    "handle_hex": item.handle_hex,
                    "category": item.category,
                    "type_key": item.type_key,
                    "position": item.position,
                    "size_text": item.size_text,
                    "count": item.count,
                    "total_weight": round(item.total_weight, 3),
                    "editable": bool(item.editable_count),
                }
                for item in info.inventory
            ],
        },
        ensure_ascii=False,
    )


def prepare(money: int | None, stacks_json: str) -> str:
    """Apply staged edits to the analyzed bytes and keep the result in memory."""

    data = _state.get("data")
    if data is None:
        raise sf.SaveError("Сначала открой сейв")

    stacks = tuple((int(handle), int(count)) for handle, count in json.loads(stacks_json))
    plan = EditPlan(
        source=SourceRef(
            kind="local",
            locator=str(_state.get("name") or "save.sav"),
            sha256=str(_state["sha256"]),
        ),
        money=None if money is None else int(money),
        stacks=stacks,
    )
    prepared = prepare_edit(data, plan)
    _state["output"] = prepared.data

    before = sf.inspect_save(data)
    after = sf.inspect_save(prepared.data)
    before_counts = {item.handle: item.count for item in before.inventory}
    after_counts = {item.handle: item.count for item in after.inventory}
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
            "source_unchanged": hashlib.sha256(data).hexdigest() == _state["sha256"],
        },
        ensure_ascii=False,
    )


def output_bytes() -> bytes:
    data = _state.get("output")
    if data is None:
        raise sf.SaveError("Нет подготовленной копии")
    return bytes(data)
