from __future__ import annotations

import binascii
import struct
from pathlib import Path

from editor.releases import release_by_id
from editor.xray_catalog import XRayCatalogProvider


def _write_unpacked_fixture(root: Path) -> None:
    config = root / "gamedata" / "config"
    text = config / "text" / "eng"
    text.mkdir(parents=True)
    (config / "items.ltx").write_text(
        """
; fixture uses the same section/value conventions as official X-Ray items
[ammo_test]:ammo_base
class = AMMO
inv_name = st_ammo_test
inv_weight = 0.25
inv_grid_width = 1
inv_grid_height = 2
inv_grid_x = 2
inv_grid_y = 3
icons_texture = ui_icon_equipment
inv_grid_slot = 8, 9
box_size = 30

[ammo_base]
inv_max_count = 60

[device_test]
class = II_ATTCH
inv_name_short = st_device_test
inv_weight = 1.5
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (text / "st_items_weapons.xml").write_text(
        """<?xml version=\"1.0\"?>
<string_table>
  <string id=\"st_ammo_test\"><text>Test rounds</text></string>
  <string id=\"st_device_test\"><text>Test device</text></string>
</string_table>
""",
        encoding="utf-8",
    )


def _packed_fixture(path: Path, *, with_metadata: bool = False) -> None:
    item_path = b"gamedata/config/items.ltx"
    item_data = b"[ammo_packed]\nclass=AMMO\ninv_name=st_packed\n"
    name_size = 16 + len(item_path)
    header_record = struct.pack(
        "<HIII",
        name_size,
        len(item_data),
        len(item_data),
        binascii.crc32(item_data) & 0xFFFFFFFF,
    ) + item_path + struct.pack("<I", 0)
    # The archive stores data chunks after the header.  Offsets are absolute
    # file offsets, matching the public X-Ray archive reader contract.
    header_chunk = struct.pack("<II", 1, len(header_record)) + header_record
    metadata = (
        struct.pack("<II", 666, len(b"[header]\nentry_point = $fs_root$\\gamedata\\\n"))
        + b"[header]\nentry_point = $fs_root$\\gamedata\\\n"
        if with_metadata
        else b""
    )
    data_offset = len(metadata) + len(header_chunk) + 8
    header_record = struct.pack(
        "<HIII",
        name_size,
        len(item_data),
        len(item_data),
        binascii.crc32(item_data) & 0xFFFFFFFF,
    ) + item_path + struct.pack("<I", data_offset)
    header_chunk = struct.pack("<II", 1, len(header_record)) + header_record
    data_chunk = struct.pack("<II", 0, len(item_data)) + item_data
    path.write_bytes(metadata + header_chunk + data_chunk)


def _packed_archive(path: Path, entries: dict[str, bytes]) -> None:
    """Write a small official-style archive with several named entries."""

    header_body_size = sum(14 + len(name.encode("utf-8")) + 4 for name in entries)
    data_chunk_start = 8 + header_body_size + 8
    data_body = bytearray()
    records: list[bytes] = []
    for name, value in entries.items():
        name_bytes = name.encode("utf-8")
        offset = data_chunk_start + len(data_body)
        records.append(
            struct.pack(
                "<HIII",
                16 + len(name_bytes),
                len(value),
                len(value),
                binascii.crc32(value) & 0xFFFFFFFF,
            )
            + name_bytes
            + struct.pack("<I", offset)
        )
        data_body.extend(value)
    header_body = b"".join(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        struct.pack("<II", 1, len(header_body))
        + header_body
        + struct.pack("<II", 0, len(data_body))
        + data_body
    )


def test_xray_catalog_reads_ltx_and_localization_without_inventing_fields(
    tmp_path: Path,
) -> None:
    _write_unpacked_fixture(tmp_path)

    provider = XRayCatalogProvider()
    catalog = provider.load(release_by_id("stalker-cs"), tmp_path)

    assert catalog is not None
    ammo = catalog.resolve("ammo_test")
    assert ammo is not None
    assert ammo.display_name == "Test rounds"
    assert ammo.category == "ammo"
    assert ammo.unit_weight == 0.25
    assert ammo.width == 1
    assert ammo.height == 2
    assert ammo.icon_x == 2
    assert ammo.icon_y == 3
    assert ammo.icon_texture == "ui_icon_equipment"
    assert ammo.max_stack == 30
    assert ammo.slots == ("8", "9")
    assert ammo.class_name == "AMMO"
    assert ammo.serialization_family == "ammo"
    assert ammo.prototype is None
    assert ammo.source.endswith("items.ltx#ammo_test")

    device = catalog.resolve("device_test")
    assert device is not None
    assert device.display_name == "Test device"
    assert device.class_name == "II_ATTCH"
    assert device.serialization_family == "base"
    assert device.max_stack is None


def test_xray_catalog_reads_release_upgrade_ids_and_exact_item_binding(
    tmp_path: Path,
) -> None:
    _write_unpacked_fixture(tmp_path)
    upgrades = tmp_path / "gamedata" / "configs" / "weapons" / "upgrades"
    upgrades.mkdir(parents=True)
    (tmp_path / "gamedata" / "configs" / "items.ltx").write_text(
        "\n[wpn_test]\nclass = WP_AK74\ninv_name = st_wpn_test\n",
        encoding="utf-8",
    )
    relations = tmp_path / "gamedata" / "configs" / "creatures" / "game_relations.ltx"
    relations.parent.mkdir(parents=True, exist_ok=True)
    relations.write_text(
        """
[game_relations]
communities = actor, 0, stalker, 1
[communities_relations]
actor = 0, 25
stalker = -25, 0
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (upgrades / "w_test_up.ltx").write_text(
        """
[up_sect_a_test]
cost = 100

[up_a_test]
section = up_sect_a_test
property = prop_rpm
name = st_upgrade_test
icon = ui_wp_upgrade_01
""".strip()
        + "\n",
        encoding="utf-8",
    )
    text = tmp_path / "gamedata" / "configs" / "text" / "eng" / "upgrades.xml"
    text.parent.mkdir(parents=True, exist_ok=True)
    text.write_text(
        """<?xml version="1.0"?>
<string_table><string id="st_upgrade_test"><text>Test upgrade</text></string></string_table>
""",
        encoding="utf-8",
    )

    bundle = XRayCatalogProvider().load_bundle(
        release_by_id("stalker-cs"),
        tmp_path,
    )

    assert bundle is not None and bundle.upgrades is not None
    upgrade = bundle.upgrades.resolve("up_a_test")
    assert upgrade is not None
    assert upgrade.display_name == "Test upgrade"
    assert upgrade.item_key == "wpn_test"
    assert bundle.upgrades.for_item("wpn_test") == (upgrade,)


def test_xray_catalog_reads_a_small_uncompressed_xdb_fixture(tmp_path: Path) -> None:
    archive = tmp_path / "gamedata.xdb"
    _packed_fixture(archive)

    provider = XRayCatalogProvider()
    catalog = provider.load(release_by_id("stalker-cop"), tmp_path)

    assert catalog is not None
    assert catalog.resolve("ammo_packed") is not None
    assert catalog.resolve("ammo_packed").display_name is None  # type: ignore[union-attr]


def test_xray_catalog_reads_official_style_resources_archive(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    resources.mkdir()
    _packed_fixture(resources / "configs.db", with_metadata=True)

    catalog = XRayCatalogProvider().load(release_by_id("stalker-cop"), tmp_path)

    assert catalog is not None
    assert catalog.resolve("ammo_packed") is not None


def test_xray_catalog_missing_or_unsupported_root_is_none(tmp_path: Path) -> None:
    provider = XRayCatalogProvider()

    assert provider.load(release_by_id("stalker2"), tmp_path) is None
    assert provider.load(release_by_id("stalker-cs-ee"), tmp_path) is None
    assert provider.load(release_by_id("stalker-cs"), tmp_path / "missing") is None


def test_xray_catalog_rejects_an_obvious_mod_overlay(tmp_path: Path) -> None:
    _write_unpacked_fixture(tmp_path)
    (tmp_path / "gamedata" / "OGSM_CS_info.rtf").write_text(
        "community mod marker",
        encoding="utf-8",
    )

    assert XRayCatalogProvider().load(release_by_id("stalker-cs"), tmp_path) is None


def test_xray_catalog_ignores_mod_overlay_and_uses_packed_official_resources(
    tmp_path: Path,
) -> None:
    _write_unpacked_fixture(tmp_path)
    (tmp_path / "gamedata" / "OGSM_CS_info.rtf").write_text(
        "community mod marker",
        encoding="utf-8",
    )
    resources = tmp_path / "resources"
    resources.mkdir()
    _packed_fixture(resources / "configs.db", with_metadata=True)

    catalog = XRayCatalogProvider().load(release_by_id("stalker-cs"), tmp_path)

    assert catalog is not None
    assert catalog.source_root == tmp_path
    assert catalog.resolve("ammo_packed") is not None
    assert catalog.resolve("ammo_test") is None


def test_xray_catalog_reads_official_russian_localization_archive(tmp_path: Path) -> None:
    configs = {
        "configs/items.ltx": b"[ammo_packed]\nclass = AMMO\n",
        "configs/creatures/game_relations.ltx": (
            b"[game_relations]\n"
            b"communities = actor, 0, csky, 1\n"
            b"[communities_relations]\n"
            b"actor = 0, -5000\n"
            b"csky = -5000, 0\n"
        ),
    }
    _packed_archive(tmp_path / "resources" / "configs.db", configs)
    _packed_archive(
        tmp_path / "localization" / "xrussian.db",
        {
            "configs/text/rus/factions.xml": (
                b"<string_table>"
                b"<string id=\"actor\"><text>\xd0\x9d\xd0\xb0\xd1\x91\xd0\xbc\xd0\xbd\xd0\xb8\xd0\xba</text></string>"
                b"<string id=\"csky\"><text>\xd0\xa7\xd0\xb8\xd1\x81\xd1\x82\xd0\xbe\xd0\xb5 \xd0\xbd\xd0\xb5\xd0\xb1\xd0\xbe</text></string>"
                b"</string_table>"
            )
        },
    )
    (tmp_path / "gamedata" / "OGSM_CS_info.rtf").parent.mkdir(parents=True)
    (tmp_path / "gamedata" / "OGSM_CS_info.rtf").write_text(
        "official resources selected after an overlay marker",
        encoding="utf-8",
    )

    bundle = XRayCatalogProvider().load_bundle(
        release_by_id("stalker-cs"),
        tmp_path,
    )

    assert bundle is not None
    assert bundle.factions.resolve("actor").display_name == "Наёмник"
    assert bundle.factions.resolve("csky").display_name == "Чистое небо"


def test_localization_prefers_russian_tables_over_english(tmp_path: Path) -> None:
    from editor.xray_catalog import _localization

    for language, text in (("eng", "Exoskeleton"), ("rus", "Экзоскелет")):
        folder = tmp_path / "configs" / "text" / language
        folder.mkdir(parents=True)
        (folder / "st_items_outfit.xml").write_text(
            f'<string_table><string id="exo"><text>{text}</text></string></string_table>',
            encoding="utf-8",
        )

    # Preferring text/eng left Call of Pripyat names in English in a
    # Russian UI.
    assert _localization(tmp_path)["exo"] == "Экзоскелет"
