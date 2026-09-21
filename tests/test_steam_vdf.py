from __future__ import annotations

from pathlib import Path

import pytest

from editor.steam_vdf import library_paths, parse_vdf, read_text


def test_parse_vdf_preserves_windows_paths_and_nested_library_entries() -> None:
    parsed = parse_vdf(
        '"libraryfolders" { "0" "C:\\Steam" "1" { '
        '"path" "D:\\Games\\SteamLibrary" } }'
    )

    assert library_paths(parsed["libraryfolders"]) == (
        r"C:\Steam",
        r"D:\Games\SteamLibrary",
    )


def test_parse_vdf_rejects_unterminated_quoted_strings() -> None:
    with pytest.raises(ValueError, match="unterminated quoted VDF string"):
        parse_vdf('"libraryfolders" { "0" "unterminated }')


def test_read_text_accepts_utf8_bom_and_cp1251(tmp_path: Path) -> None:
    utf8 = tmp_path / "utf8.vdf"
    cp1251 = tmp_path / "cp1251.vdf"
    utf8.write_bytes("ключ".encode("utf-8-sig"))
    cp1251.write_bytes("ключ".encode("cp1251"))

    assert read_text(utf8) == "ключ"
    assert read_text(cp1251) == "ключ"
    assert read_text(tmp_path / "missing.vdf") is None
