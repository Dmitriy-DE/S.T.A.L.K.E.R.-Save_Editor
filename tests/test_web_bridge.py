"""The browser build must be the same editor, not a lookalike.

These tests run the web bridge under normal CPython: they prove the page gets
its numbers from the same parser and that a web edit produces byte-identical
output to the desktop path.  The browser-only part (Pyodide plus the WASM
decoder) is verified by hand against a real save; see docs/evidence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import web_bridge  # noqa: E402 - web/ must be on sys.path first
from test_xray_save import _fixture  # noqa: E402

import editor.codec as codec  # noqa: E402
from editor.capabilities import FormatCapabilities  # noqa: E402
from editor.models import EditPlan, SourceRef  # noqa: E402
from editor.prepare import prepare_edit  # noqa: E402


def test_analyze_reports_the_same_numbers_as_the_parser(synthetic_save: bytes) -> None:
    import save_format as sf

    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))
    info = sf.inspect_save(synthetic_save)

    assert snapshot["money"] == info.money
    assert snapshot["sha256"] == info.sha256
    assert snapshot["crc_ok"] is info.crc_ok
    assert snapshot["inventory_count"] == len(info.inventory)
    assert len(snapshot["inventory"]) == len(info.inventory)


def test_analyze_exposes_release_edition_and_capabilities_from_registry(
    synthetic_save: bytes,
) -> None:
    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))

    assert snapshot["release_id"] == "stalker2"
    assert snapshot["edition"] == "s2"
    assert snapshot["capabilities"]["read_inventory"] is True
    assert snapshot["capabilities"]["edit_money"] is True
    assert snapshot["capabilities"]["add_items"] is False
    assert snapshot["catalog_available"] is False


def test_web_snapshot_gates_editable_rows_with_format_capabilities(
    monkeypatch: pytest.MonkeyPatch, synthetic_save: bytes
) -> None:
    import save_format as sf

    readonly = SimpleNamespace(
        id="readonly-fixture",
        title="Read-only fixture",
        release_id="readonly-fixture",
        edition="test",
        capabilities=FormatCapabilities(read_inventory=True),
        inspect=lambda payload: sf.inspect_save(payload),
    )
    monkeypatch.setattr(web_bridge, "detect_or_raise", lambda *args, **kwargs: readonly)

    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))

    assert snapshot["money_editable"] is False
    assert all(item["editable"] is False for item in snapshot["inventory"])


def test_metadata_table_matches_the_desktop_rows(synthetic_save: bytes) -> None:
    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))
    names = [row[0] for row in snapshot["metadata"]]

    # The same parser-backed rows the Qt overview shows, and nothing invented.
    assert names[:3] == ["Файл", "CRC-32", "SHA-256"]
    assert snapshot["metadata"][-1][:2] == ["UE5 GVAS schema", "не разобрана"]


def test_web_edit_is_byte_identical_to_the_desktop_edit(synthetic_save: bytes) -> None:
    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))
    result = json.loads(web_bridge.prepare(900_000, json.dumps([[0x30000001, 3]])))

    plan = EditPlan(
        source=SourceRef(
            kind="local",
            locator="slot.sav",
            sha256=snapshot["sha256"],
        ),
        money=900_000,
        stacks=((0x30000001, 3),),
    )
    desktop = prepare_edit(synthetic_save, plan)

    assert result["output_sha256"] == desktop.output_sha256
    assert web_bridge.output_bytes() == desktop.data
    assert result["source_unchanged"] is True


def test_prepare_without_an_open_save_is_refused() -> None:
    from save_format import SaveError

    web_bridge._state.clear()
    with pytest.raises(SaveError, match="Сначала открой сейв"):
        web_bridge.prepare(1, "[]")
    with pytest.raises(SaveError, match="подготовленной"):
        web_bridge.output_bytes()


def test_install_decoder_routes_through_the_registered_decoder() -> None:
    calls: list[tuple[bytes, int]] = []

    def fake_call(stream, size):
        calls.append((bytes(stream), size))
        return b"y" * size

    web_bridge.install_decoder(fake_call)
    try:
        assert codec.decompress(b"packed", 3) == b"yyy"
        assert calls == [(b"packed", 3)]
    finally:
        codec.clear_registered_decoder()


def test_web_bridge_reads_and_edits_an_original_xray_save() -> None:
    data = _fixture()

    snapshot = json.loads(web_bridge.analyze(data, "slot.scop"))
    assert snapshot["format_id"] == "stalker-cop"
    assert snapshot["release_id"] == "stalker-cop"
    assert snapshot["edition"] == "original"
    assert snapshot["capabilities"]["edit_stacks"] is True
    assert snapshot["capabilities"]["add_items"] is True
    assert snapshot["capabilities"]["remove_items"] is True
    assert snapshot["catalog_available"] is True
    assert snapshot["catalog_source"] == "save-observed"
    assert snapshot["crc_present"] is False
    assert snapshot["money"] == 1234
    assert snapshot["inventory"][0]["name"] == "ammo_9x39_pab9"
    assert snapshot["inventory"][0]["total_weight"] is None
    assert all(row[0] != "UE5 GVAS schema" for row in snapshot["metadata"])

    result = json.loads(web_bridge.prepare(9876, json.dumps([[0x1234, 44]])))

    assert result["money"] == [1234, 9876]
    assert result["stacks"] == [["0x00001234", 30, 44]]
    assert result["source_unchanged"] is True


def test_web_bridge_can_stage_an_observed_xray_item_addition_and_removal() -> None:
    data = _fixture()
    snapshot = json.loads(web_bridge.analyze(data, "slot.scop"))
    item_key = snapshot["inventory"][0]["type_key"]

    added = json.loads(
        web_bridge.prepare(
            None,
            "[]",
            json.dumps([[item_key, 2]]),
        )
    )
    assert added["adds"]
    assert added["adds"][0][1] == item_key

    removed = json.loads(
        web_bridge.prepare(
            None,
            "[]",
            "[]",
            json.dumps([[snapshot["inventory"][0]["handle"], True]]),
        )
    )
    assert removed["removed"] == [snapshot["inventory"][0]["handle_hex"]]


def test_web_bridge_treats_pyodide_js_null_as_no_money() -> None:
    data = _fixture()
    web_bridge.analyze(data, "slot.scop")

    class JsNull:
        def __int__(self) -> int:
            raise AssertionError("JS null must not be coerced to int")

    result = json.loads(web_bridge.prepare(JsNull(), "[]"))

    assert result["money"] == [1234, 1234]


def test_analyze_clears_a_prepared_output_from_the_previous_save() -> None:
    from save_format import SaveError

    data = _fixture()
    snapshot = json.loads(web_bridge.analyze(data, "slot.scop"))
    web_bridge.prepare(
        None,
        "[]",
        json.dumps([[snapshot["inventory"][0]["type_key"], 1]]),
    )

    web_bridge.analyze(data, "another-slot.scop")

    with pytest.raises(SaveError, match="подготовленной"):
        web_bridge.output_bytes()


def test_web_bridge_accepts_generated_official_catalog_metadata() -> None:
    web_bridge.install_catalogs(
        json.dumps(
            {
                "schema_version": 1,
                "releases": {
                    "stalker-cop": {
                        "items": [
                            {
                                "key": "ammo_9x39_pab9",
                                "category": "ammo",
                                "max_stack": 30,
                                "serialization_family": "ammo",
                            }
                        ]
                    }
                },
            }
        )
    )
    snapshot = json.loads(web_bridge.analyze(_fixture(), "slot.scop"))

    assert snapshot["catalog_source"] == "generated-official"
    assert snapshot["catalog_items"][0]["key"] == "ammo_9x39_pab9"
