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

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import web_bridge  # noqa: E402 - web/ must be on sys.path first

import editor.codec as codec  # noqa: E402
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


def test_metadata_table_matches_the_desktop_rows(synthetic_save: bytes) -> None:
    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))
    names = [row[0] for row in snapshot["metadata"]]

    # The same parser-backed rows the Qt overview shows, and nothing invented.
    assert names[:3] == ["Файл", "CRC-32", "SHA-256"]
    assert snapshot["metadata"][-1][:2] == ["UE5 GVAS schema", "не разобрана"]


def test_web_edit_is_byte_identical_to_the_desktop_edit(synthetic_save: bytes) -> None:
    web_bridge.analyze(synthetic_save, "slot.sav")
    result = json.loads(web_bridge.prepare(900_000, json.dumps([[0x30000001, 3]])))

    plan = EditPlan(
        source=SourceRef(
            kind="local",
            locator="slot.sav",
            sha256=json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))["sha256"],
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
