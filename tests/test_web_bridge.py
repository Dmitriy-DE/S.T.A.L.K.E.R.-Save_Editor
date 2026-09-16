"""The browser build must be the same editor, not a lookalike.

These tests run the web bridge under normal CPython: they prove the page gets
its numbers from the same parser and that a web edit produces byte-identical
output to the desktop path.  The browser-only part (Pyodide plus the WASM
decoder) is verified by hand against a real save; see docs/evidence.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import web_bridge  # noqa: E402 - web/ must be on sys.path first
from test_xray_durability import _condition_fixture  # noqa: E402
from test_xray_save import _fixture, _relation_registry  # noqa: E402

import editor.codec as codec  # noqa: E402
from editor.capabilities import FormatCapabilities  # noqa: E402


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
    assert snapshot["capabilities"]["edit_money"] is False
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


def test_web_edit_is_refused_until_gameplay_is_verified(synthetic_save: bytes) -> None:
    from save_format import SaveError

    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))
    with pytest.raises(SaveError, match="read-only"):
        web_bridge.prepare(900_000, json.dumps([[0x30000001, 3]]))
    assert snapshot["money_editable"] is False


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


def test_web_bridge_exposes_and_prepares_experimental_faction_edits() -> None:
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
                        ],
                        "factions": [
                            {
                                "key": "actor",
                                "display_name": "Actor",
                                "numeric_id": 0,
                                "source": "fixture",
                                "release_id": "stalker-cop",
                            },
                            {
                                "key": "bandit",
                                "display_name": "Bandit",
                                "numeric_id": 1,
                                "source": "fixture",
                                "release_id": "stalker-cop",
                            },
                        ],
                        "goodwill_min": -3000,
                        "goodwill_max": 1000,
                        "attitude_neutral_threshold": -999,
                        "attitude_friend_threshold": 999,
                    }
                },
            }
        )
    )
    data = _fixture(
        community=0,
        registry=_relation_registry(actor_values=((0, 125), (1, -240))),
    )

    snapshot = json.loads(web_bridge.analyze(data, "slot.scop"))

    assert snapshot["player_faction_index"] == 0
    assert snapshot["player_faction_key"] == "actor"
    assert snapshot["faction_goodwill_min"] == -3000
    assert snapshot["faction_goodwill_max"] == 1000
    assert [row["value"] for row in snapshot["faction_relations"]] == [125, -240]
    assert all(row["stored"] for row in snapshot["faction_relations"])
    assert snapshot["capabilities"]["edit_relations"] is True
    assert snapshot["capabilities"]["edit_player_faction"] is True
    assert "edit_relations" in snapshot["capabilities"]["experimental_fields"]
    assert "edit_player_faction" in snapshot["capabilities"]["experimental_fields"]

    result = json.loads(
        web_bridge.prepare(
            None,
            "[]",
            "[]",
            "[]",
            "[]",
            "[]",
            json.dumps([["bandit", 375]]),
            "bandit",
        )
    )
    assert result["faction_relations"] == [["bandit", -240, 375]]
    assert result["player_faction"] == [0, 1]


def test_web_bridge_prepares_faction_edits_when_capability_is_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                        ],
                        "factions": [
                            {
                                "key": "actor",
                                "numeric_id": 0,
                                "source": "fixture",
                                "release_id": "stalker-cop",
                            },
                            {
                                "key": "bandit",
                                "numeric_id": 1,
                                "source": "fixture",
                                "release_id": "stalker-cop",
                            },
                        ],
                        "goodwill_min": -3000,
                        "goodwill_max": 1000,
                    }
                },
            }
        )
    )
    data = _fixture(
        community=0,
        registry=_relation_registry(actor_values=((0, 125), (1, -240))),
    )
    web_bridge.analyze(data, "slot.scop")
    format_ = web_bridge._state["format"]
    monkeypatch.setattr(
        format_,
        "capabilities",
        replace(
            format_.capabilities,
            edit_relations=True,
            edit_player_faction=True,
        ),
    )

    result = json.loads(
        web_bridge.prepare(
            None,
            "[]",
            "[]",
            "[]",
            "[]",
            "[]",
            json.dumps([["bandit", 375]]),
            "bandit",
        )
    )

    assert result["faction_relations"] == [["bandit", -240, 375]]
    assert result["player_faction"] == [0, 1]


def test_web_bridge_exposes_and_prepares_experimental_condition_edit() -> None:
    data = _condition_fixture(version=128, outer=6)
    snapshot = json.loads(web_bridge.analyze(data, "condition.scop"))
    item = snapshot["inventory"][0]

    assert item["condition"] == pytest.approx(0.25)
    assert item["condition_editable"] is True
    assert item["storage"] is None
    assert snapshot["capabilities"]["edit_durability"] is True
    assert "edit_durability" in snapshot["capabilities"]["experimental_fields"]

    result = json.loads(
        web_bridge.prepare(
            None,
            "[]",
            "[]",
            "[]",
            "[]",
            json.dumps([[0x3456, 0.75]]),
        )
    )
    assert result["durability"] == [["0x00003456", pytest.approx(0.25), pytest.approx(0.75)]]


def test_web_bridge_exposes_confirmed_xray_storage_place() -> None:
    data = _condition_fixture(version=128, outer=6, client_place=0x0411)
    snapshot = json.loads(web_bridge.analyze(data, "equipped.scop"))
    item = snapshot["inventory"][0]

    assert item["storage"] == "equipped"
    assert item["position"] == "экипировано (слот подтверждён)"


def test_web_bridge_prepares_xray_structural_edits_after_owner_acceptance() -> None:
    data = _fixture()
    snapshot = json.loads(web_bridge.analyze(data, "slot.scop"))
    item_key = snapshot["inventory"][0]["type_key"]

    added = json.loads(web_bridge.prepare(None, "[]", json.dumps([[item_key, 2]])))
    assert added["adds"]

    web_bridge.analyze(data, "slot.scop")
    removed = json.loads(
        web_bridge.prepare(
            None,
            "[]",
            "[]",
            json.dumps([[snapshot["inventory"][0]["handle"], True]]),
        )
    )
    assert removed["removed"]


def test_web_bridge_treats_pyodide_js_null_as_no_money() -> None:
    data = _fixture()
    web_bridge.analyze(data, "slot.scop")

    class JsNull:
        def __int__(self) -> int:
            raise AssertionError("JS null must not be coerced to int")

    result = json.loads(web_bridge.prepare(JsNull(), "[]"))

    assert result["money"] == [1234, 1234]


def test_analyze_clears_a_prepared_output_from_the_previous_save() -> None:
    data = _fixture()
    web_bridge.analyze(data, "slot.scop")
    web_bridge._state["output"] = b"old prepared output"

    web_bridge.analyze(data, "another-slot.scop")

    from save_format import SaveError

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
                                "display_name": "Патроны 9x39",
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
    assert snapshot["catalog_items"][0]["name"] == "Патроны 9x39"


def test_web_bridge_exposes_and_prepares_release_catalog_upgrades() -> None:
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
                                "icon_x": 2,
                                "icon_y": 3,
                                "icon_texture": "ui_icon_equipment",
                            }
                        ],
                        "upgrades": [
                            {
                                "key": "up_a_new",
                                "display_name": "New A",
                                "category": "weapon",
                                "item_key": "ammo_9x39_pab9",
                                "applicable_item_keys": ["ammo_9x39_pab9"],
                                "property": "fire_wound_immunity",
                                "source": "fixture",
                                "release_id": "stalker-cop",
                            },
                            {
                                "key": "up_c_new",
                                "display_name": "New C",
                                "category": "weapon",
                                "item_key": "ammo_9x39_pab9",
                                "applicable_item_keys": ["ammo_9x39_pab9"],
                                "source": "fixture",
                                "release_id": "stalker-cop",
                            },
                        ],
                    }
                },
            }
        )
    )
    data = _fixture(upgrades=("up_a_old",))
    snapshot = json.loads(web_bridge.analyze(data, "slot.scop"))

    assert snapshot["upgrade_catalog_available"] is True
    assert snapshot["catalog_items"][0]["icon_x"] == 2
    assert snapshot["inventory"][0]["upgrades"] == ["up_a_old"]
    assert snapshot["inventory"][0]["upgrade_editable"] is True
    assert snapshot["inventory"][0]["icon_x"] == 2
    assert snapshot["inventory"][0]["icon_y"] == 3

    result = json.loads(
        web_bridge.prepare(
            None,
            "[]",
            "[]",
            "[]",
            json.dumps([[0x1234, ["up_a_new", "up_c_new"]]]),
        )
    )
    assert result["upgrades"] == [
        ["0x00001234", ["up_a_old"], ["up_a_new", "up_c_new"]]
    ]
