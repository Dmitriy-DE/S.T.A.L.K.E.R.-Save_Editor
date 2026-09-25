"""Translations, S2 slot metadata, preferences, save comparison and UI sounds."""

from __future__ import annotations

import struct
import wave
from dataclasses import replace
from pathlib import Path

import pytest

from editor import i18n
from editor.compare import compare_saves
from editor.preferences import Preferences, load_preferences, save_preferences
from editor.s2_campaigns import parse_campaigns, region_slug
from tools import i18n_extract


@pytest.fixture
def language():
    def switch(code: str) -> None:
        i18n.set_language(code)

    yield switch
    i18n.set_language("ru")


def test_every_locale_covers_every_message_with_matching_placeholders() -> None:
    assert i18n_extract.check(i18n_extract.collect()) == []


def test_tr_translates_formats_and_falls_back_to_source(language) -> None:
    language("en")
    assert i18n.tr("Сохранить") == "Save"
    assert i18n.tr("Здоровье: {0}%", 87) == "Health: 87%"
    assert i18n.tr("Строки нет в каталоге {0}", 1) == "Строки нет в каталоге 1"
    language("ru")
    assert i18n.tr("Здоровье: {0}%", 87) == "Здоровье: 87%"


@pytest.mark.parametrize(
    ("code", "count", "expected"),
    [
        ("ru", 1, "сохранение"),
        ("ru", 3, "сохранения"),
        ("ru", 11, "сохранений"),
        ("uk", 22, "збереження"),
        ("uk", 25, "збережень"),
        ("en", 1, "save"),
        ("en", 2, "saves"),
        ("pl", 1, "zapis"),
        ("pl", 3, "zapisy"),
        ("pl", 5, "zapisów"),
        ("fr", 0, "sauvegarde"),
        ("ja", 7, "件のセーブ"),
    ],
)
def test_plural_rules_per_language(language, code: str, count: int, expected: str) -> None:
    language(code)
    assert i18n.trn(count, "сохранение", "сохранения", "сохранений") == expected


def test_source_text_maps_translated_status_back_to_russian(language) -> None:
    language("de")
    message = i18n.tr("Запись в облако недоступна: {0}; запись не начиналась", "offline")
    assert message != i18n.source_text(message)
    assert i18n.source_text(message) == "Запись в облако недоступна: offline; запись не начиналась"


def test_language_normalisation() -> None:
    assert i18n._normalise("pt-BR") == "pt_BR"
    assert i18n._normalise("zh_HK") == "zh_TW"
    assert i18n._normalise("uk_UA.UTF-8") == "uk"
    assert i18n._normalise("xx") is None


def _campaign(records: list[tuple[str, int, float, str, str]]) -> bytes:
    out = bytearray(struct.pack("<II", 0xBB, 0) + b"\x00\x01\x00\x06\x00Slot_02\x00")
    strings: list[str] = []

    def string(text: str) -> bytes:
        if text in strings:
            return struct.pack("<H", strings.index(text))
        strings.append(text)
        return struct.pack("<HH", len(strings) - 1, len(text)) + text.encode()

    for index, (guid, ticks, seconds, region, quest) in enumerate(records):
        guid_bytes = struct.pack("<4I", *(int(guid[i : i + 8], 16) for i in range(0, 32, 8)))
        out += struct.pack("<I", index) + guid_bytes + struct.pack("<IIqf", 3, 0xBB, ticks, seconds)
        out += string(region) + string(quest) + b"\x0f" + b"\x00" * 5
    return bytes(out + b"Achievements")


def test_campaign_index_yields_region_and_play_time() -> None:
    ticks = 639_000_000_000_000_000
    raw = _campaign(
        [
            ("99457897416AC2273A59B5826C7F6306", ticks, 7200.0, "sid_locations_region_yanov_name", "Q1"),
            ("2B8270124B24848CEF011F8F103A4DA1", ticks, 3600.0, "sid_locations_region_yanov_name", "Q2"),
        ]
    )
    records = parse_campaigns(raw)
    assert set(records) == {"99457897416AC2273A59B5826C7F6306", "2B8270124B24848CEF011F8F103A4DA1"}
    first = records["99457897416AC2273A59B5826C7F6306"]
    assert region_slug(first.region_key) == "yanov"
    assert first.play_hours == pytest.approx(2.0)
    assert records["2B8270124B24848CEF011F8F103A4DA1"].region_key == first.region_key


def test_campaign_parser_stops_on_garbage_instead_of_guessing() -> None:
    assert parse_campaigns(b"\x00" * 64) == {}


def test_preferences_round_trip_and_tolerate_bad_values(tmp_path: Path) -> None:
    path = tmp_path / "preferences.json"
    save_preferences(Preferences(language="uk", sound=False, sound_volume=40, motion=False), path)
    assert load_preferences(path) == Preferences("uk", False, 40, False)
    path.write_text('{"sound": "yes", "sound_volume": 900, "language": 5}', encoding="utf-8")
    assert load_preferences(path) == Preferences(sound_volume=100)
    path.write_text("not json", encoding="utf-8")
    assert load_preferences(path) == Preferences()


def test_compare_saves_reports_money_items_and_actor_changes() -> None:
    from save_format import InventoryItem, SaveInfo

    def item(key: str, count: int) -> InventoryItem:
        return InventoryItem(
            handle=hash(key) & 0xFFFF, x=None, y=None, width=None, height=None, cells=(),
            count=count, total_weight=None, unit_weight=None, kind_code=0, category="",
            record_offset=0, record_end_guess=0, fingerprint="", type_key=key,
            editable_count=False, display_name=key,
        )

    base = SaveInfo(1, 1, 0, 0, True, "", 100, 1, inventory=(item("medkit", 2), item("bread", 1)))
    after = replace(base, money=150, inventory=(item("medkit", 5),), actor_health=0.5)
    rows = {(row.kind, row.label): (row.before, row.after) for row in compare_saves(base, after)}
    assert rows[("money", "Деньги")] == ("100", "150")
    assert rows[("item", "medkit")] == ("2", "5")
    assert rows[("item", "bread")] == ("1", "—")
    assert rows[("actor", "Здоровье")] == ("—", "50%")
    assert compare_saves(base, base) == ()


def test_ui_sounds_are_short_quiet_mono_wavs(tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from ui.effects import SOUND_EVENTS, _render, sound_theme, write_wav

    assert sound_theme("stalker2-heart-of-chornobyl") == "stalker2"
    assert sound_theme("stalker-cop") == "cop"
    for theme in ("soc", "clear_sky", "cop", "stalker2"):
        for event in SOUND_EVENTS:
            path = tmp_path / f"{theme}-{event}.wav"
            write_wav(path, _render(event, theme))
            with wave.open(str(path)) as handle:
                assert handle.getnchannels() == 1
                assert handle.getnframes() / handle.getframerate() < 0.4


def test_packaged_app_bundles_the_trilogy_catalog() -> None:
    spec = (Path(__file__).resolve().parents[1] / "packaging" / "editor.spec").read_text(encoding="utf-8")
    assert '"web" / "catalogs.json"' in spec


def test_official_names_cover_the_catalog_in_every_shipped_language() -> None:
    import json

    from editor.official_names import NAMES_PATH, release_family

    names = json.loads(NAMES_PATH.read_text(encoding="utf-8"))
    catalogs = json.loads((NAMES_PATH.parent / "catalogs.json").read_text(encoding="utf-8"))["releases"]
    assert len(names["languages"]) == 13
    for release_id, bundle in catalogs.items():
        table = names["releases"][release_family(release_id)]
        for item in bundle["items"]:
            if item.get("display_name"):
                assert set(table["items"][item["key"]]) == set(names["languages"]), item["key"]
        for upgrade in bundle["upgrades"]:
            assert upgrade["key"] in table["upgrades"]


def test_official_name_follows_the_interface_language(language) -> None:
    from editor.official_names import official_name

    language("de")
    assert official_name("stalker-cop", "items", "bandage") == "Verband"
    language("pt_BR")  # the games were not released in Portuguese
    assert official_name("stalker-cop-ee", "items", "bandage") == "Bandage"
    language("uk")
    assert official_name("stalker-cop", "items", "jup_b200_tech_materials_wire").startswith("Моток")
    assert official_name("stalker-cs", "items", "wpn_binoc") == "Бінокль"
    assert official_name("stalker2", "items", "bandage") is None


def test_item_label_prefers_official_names_but_keeps_mod_names_in_russian(language) -> None:
    from editor.catalog import ItemDefinition, catalog_from_items
    from editor.item_names import item_label
    from save_format import InventoryItem

    row = InventoryItem(
        handle=1, x=None, y=None, width=None, height=None, cells=(), count=None,
        total_weight=None, unit_weight=None, kind_code=0, category="", record_offset=0,
        record_end_guess=0, fingerprint="", type_key="wpn_val", editable_count=False,
        display_name="wpn_val",
    )
    mod = catalog_from_items(
        "stalker-cs",
        (
            ItemDefinition(
                key="wpn_val", display_name="АС «Вал»", category="weapon", unit_weight=None,
                width=None, height=None, max_stack=None, slots=(), prototype=None, source="mod",
            ),
        ),
    )
    language("en")
    assert item_label(row, mod, release_id="stalker-cs", modded=True) == 'SA "Avalanche"'
    language("ru")
    assert item_label(row, mod, release_id="stalker-cs", modded=True) == "АС «Вал»"
    assert item_label(row, None, release_id="stalker-cs") == "СА «ЛАВИНА»"


def test_game_audio_joins_mono_halves_and_prefers_the_original_install(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("PySide6")
    from types import SimpleNamespace

    import ui.game_audio as game_audio

    left, right = struct.pack("<3h", 1, 2, 3), struct.pack("<2h", -1, -2)
    assert struct.unpack("<6h", game_audio.interleave(left, right)) == (1, -1, 2, -2, 3, 0)

    audio = game_audio.GameAudio(tmp_path)
    assert audio.music_path("soc").suffix == ".wav"  # two mono halves → stereo WAV
    assert audio.music_path("cop").suffix == ".ogg"  # one file stays compressed
    assert not audio.has_event("stalker2", "click")

    ee, original = tmp_path / "ee", tmp_path / "original"
    ee.mkdir()
    original.mkdir()
    monkeypatch.setattr(
        game_audio,
        "installed_releases",
        lambda: (
            SimpleNamespace(release_id="stalker-cop-ee", install_dir=str(ee)),
            SimpleNamespace(release_id="stalker-cop", install_dir=str(original)),
        ),
    )
    assert game_audio.install_root("cop") == original
    assert game_audio.install_root("soc") is None
