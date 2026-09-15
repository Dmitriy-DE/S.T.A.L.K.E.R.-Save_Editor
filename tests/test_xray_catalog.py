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


def _packed_fixture(path: Path) -> None:
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
    data_offset = len(header_chunk) + 8
    header_record = struct.pack(
        "<HIII",
        name_size,
        len(item_data),
        len(item_data),
        binascii.crc32(item_data) & 0xFFFFFFFF,
    ) + item_path + struct.pack("<I", data_offset)
    header_chunk = struct.pack("<II", 1, len(header_record)) + header_record
    data_chunk = struct.pack("<II", 0, len(item_data)) + item_data
    path.write_bytes(header_chunk + data_chunk)


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
    assert ammo.max_stack == 30
    assert ammo.slots == ("8", "9")
    assert ammo.prototype is None
    assert ammo.source.endswith("items.ltx#ammo_test")

    device = catalog.resolve("device_test")
    assert device is not None
    assert device.display_name == "Test device"
    assert device.max_stack is None


def test_xray_catalog_reads_a_small_uncompressed_xdb_fixture(tmp_path: Path) -> None:
    archive = tmp_path / "gamedata.xdb"
    _packed_fixture(archive)

    provider = XRayCatalogProvider()
    catalog = provider.load(release_by_id("stalker-cop"), tmp_path)

    assert catalog is not None
    assert catalog.resolve("ammo_packed") is not None
    assert catalog.resolve("ammo_packed").display_name is None  # type: ignore[union-attr]


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
