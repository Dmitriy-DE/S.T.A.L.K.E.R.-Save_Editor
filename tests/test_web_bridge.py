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
from test_xray_durability import _condition_fixture  # noqa: E402
from test_xray_relations import _registry  # noqa: E402
from test_xray_save import _fixture  # noqa: E402

import editor.codec as codec  # noqa: E402
from editor.capabilities import FormatCapabilities  # noqa: E402
from editor.formats import by_id  # noqa: E402


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
    assert snapshot["capabilities"]["experimental_fields"] == [
        "edit_durability",
        "edit_money",
    ]
    assert snapshot["capabilities"]["edit_durability"] is True
    assert snapshot["capabilities"]["edit_stacks"] is False
    assert snapshot["capabilities"]["add_items"] is False
    assert snapshot["catalog_available"] is False
    assert snapshot["capabilities"] == by_id("stalker2").capabilities.as_dict()


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


def test_web_money_edit_is_experimental_but_stack_edit_is_refused(
    synthetic_save: bytes,
) -> None:
    from save_format import SaveError

    snapshot = json.loads(web_bridge.analyze(synthetic_save, "slot.sav"))
    result = json.loads(web_bridge.prepare(900_000, "[]"))
    assert result["money"] == [100, 900_000]
    with pytest.raises(SaveError, match="не подтверждено"):
        web_bridge.prepare(None, json.dumps([[0x30000001, 3]]))
    assert snapshot["money_editable"] is True


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
    assert snapshot["inventory"][0]["name"] == "9х39 мм СП-5"  # official CoP name
    assert snapshot["inventory"][0]["total_weight"] is None
    assert {
        "icon_x",
        "icon_y",
        "icon_texture",
    }.issubset(snapshot["inventory"][0])
    assert all(row[0] != "UE5 GVAS schema" for row in snapshot["metadata"])

    result = json.loads(web_bridge.prepare(9876, json.dumps([[0x1234, 44]])))
    assert result["money"] == [1234, 9876]
    assert result["stacks"] == [["0x00001234", 30, 44]]


def test_web_bridge_exposes_and_prepares_experimental_condition_edit() -> None:
    data = _condition_fixture(version=128, outer=6)
    snapshot = json.loads(web_bridge.analyze(data, "condition.scop"))
    item = snapshot["inventory"][0]

    assert item["condition"] == pytest.approx(0.25)
    assert item["condition_editable"] is True
    assert snapshot["capabilities"]["edit_durability"] is True
    assert "edit_durability" in snapshot["capabilities"]["experimental_fields"]

    result = json.loads(
        web_bridge.prepare(None, "[]", "[]", "[]", json.dumps([[0x3456, 0.75]]))
    )
    assert result["durability"] == [
        ["0x00003456", pytest.approx(0.25), pytest.approx(0.75)]
    ]


def test_web_bridge_exposes_confirmed_xray_storage_place() -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=1 | (2 << 4) | (3 << 10),
    )
    snapshot = json.loads(web_bridge.analyze(data, "equipped.scop"))
    item = snapshot["inventory"][0]

    assert item["storage"] == "equipped"
    assert item["position"] == "экипировано (слот 2)"
    assert item["placement_type"] == "slot"
    assert item["placement_slot"] == 2
    assert item["placement_base_slot"] == 3
    assert item["placement_editable"] is True
    assert snapshot["capabilities"]["edit_placement"] is True


def test_web_bridge_exposes_per_item_delete_safety() -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=1 | (2 << 4) | (3 << 10),
    )

    snapshot = json.loads(web_bridge.analyze(data, "equipped.scop"))
    item = snapshot["inventory"][0]

    assert item["remove_editable"] is False
    assert "equipped" in item["remove_reason"]


def test_web_bridge_prepares_xray_inventory_placement() -> None:
    data = _condition_fixture(
        version=128,
        outer=6,
        client_place=1 | (2 << 4) | (3 << 10),
    )
    snapshot = json.loads(web_bridge.analyze(data, "placement.scop"))
    assert snapshot["capabilities"]["edit_placement"] is True

    result = json.loads(
        web_bridge.prepare(
            None,
            "[]",
            "[]",
            "[]",
            "[]",
            "[]",
            "null",
            "[]",
            json.dumps([[0x3456, "slot", 4]]),
        )
    )

    assert result["placements"] == [
        ["0x00003456", ["slot", 2], ["slot", 4]]
    ]


def test_web_bridge_exposes_and_prepares_xray_faction_relations() -> None:
    payload = {
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
                    },
                    {
                        "key": "bandit",
                        "display_name": "Bandit",
                        "numeric_id": 1,
                        "source": "fixture",
                    },
                ],
                "goodwill_min": -3000,
                "goodwill_max": 1000,
            }
        },
    }
    old_items = web_bridge._catalogs.get("stalker-cop")
    old_factions = web_bridge._faction_catalogs.get("stalker-cop")
    try:
        web_bridge.install_catalogs(json.dumps(payload))
        data = _fixture(registry=_registry())
        snapshot = json.loads(web_bridge.analyze(data, "relations.scop"))

        assert snapshot["capabilities"]["edit_relations"] is True
        assert snapshot["faction_catalog_available"] is True
        assert snapshot["faction_relations_editable"] is True
        assert [(row["key"], row["value"]) for row in snapshot["faction_relations"]] == [
            ("actor", 100),
            ("bandit", -100),
        ]

        result = json.loads(
            web_bridge.prepare(
                None,
                "[]",
                "[]",
                "[]",
                "[]",
                json.dumps([["bandit", 375]]),
            )
        )
        assert result["faction_relations"] == [["bandit", -100, 375]]
    finally:
        if old_items is None:
            web_bridge._catalogs.pop("stalker-cop", None)
        else:
            web_bridge._catalogs["stalker-cop"] = old_items
        if old_factions is None:
            web_bridge._faction_catalogs.pop("stalker-cop", None)
        else:
            web_bridge._faction_catalogs["stalker-cop"] = old_factions


def test_web_bridge_exposes_and_prepares_player_faction() -> None:
    payload = {
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
                    },
                    {
                        "key": "bandit",
                        "display_name": "Bandit",
                        "numeric_id": 1,
                        "source": "fixture",
                    },
                ],
            }
        },
    }
    old_items = web_bridge._catalogs.get("stalker-cop")
    old_factions = web_bridge._faction_catalogs.get("stalker-cop")
    try:
        web_bridge.install_catalogs(json.dumps(payload))
        data = _fixture(player_community=0)
        snapshot = json.loads(web_bridge.analyze(data, "player-faction.scop"))

        assert snapshot["player_faction_index"] == 0
        assert snapshot["player_faction_editable"] is True
        assert snapshot["capabilities"]["edit_player_faction"] is True

        result = json.loads(
            web_bridge.prepare(
                None,
                "[]",
                "[]",
                "[]",
                "[]",
                "[]",
                json.dumps("bandit"),
            )
        )
        assert result["player_faction"] == [0, 1]
    finally:
        if old_items is None:
            web_bridge._catalogs.pop("stalker-cop", None)
        else:
            web_bridge._catalogs["stalker-cop"] = old_items
        if old_factions is None:
            web_bridge._faction_catalogs.pop("stalker-cop", None)
        else:
            web_bridge._faction_catalogs["stalker-cop"] = old_factions


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
