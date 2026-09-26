"""PyInstaller spec for the GUI and a console diagnostic companion."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path, PurePath

from PyInstaller.building.build_main import Analysis, EXE, COLLECT, PYZ


_root_from_env = os.environ.get("SAVE_EDITOR_ROOT")
ROOT = Path(_root_from_env or Path.cwd()).resolve()
TARGET = os.environ.get("SAVE_EDITOR_TARGET", "linux").strip().lower()
_encoder_dir_text = os.environ.get("SAVE_EDITOR_ENCODER_DIR", "").strip()
ENCODER_DIR = Path(_encoder_dir_text).resolve() if _encoder_dir_text else None
if ENCODER_DIR is not None and ENCODER_DIR.is_dir():
    sys.path.insert(0, str(ENCODER_DIR))

datas: list[tuple[str, str]] = []
for filename in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "VERSION"):
    path = ROOT / filename
    if path.is_file():
        datas.append((str(path), "."))
for filename in ("README.md", "STATUS.md"):
    path = ROOT / "docs" / filename
    if path.is_file():
        datas.append((str(path), "docs"))
data_dir = ROOT / "data"
if data_dir.is_dir():
    datas.append((str(data_dir), "data"))
# Application icon (original artwork) for the window/taskbar.
for _icon in ("app_icon.svg", "app_icon_256.png", "app_icon_128.png", "app_icon_64.png"):
    _icon_path = ROOT / "assets" / _icon
    if _icon_path.is_file():
        datas.append((str(_icon_path), "assets"))
# Bundled inventory icon pack, so icons are present without a game install.
icon_pack = ROOT / "assets" / "icons" / "xray"
if icon_pack.is_dir():
    datas.append((str(icon_pack), "assets/icons/xray"))
game_audio = ROOT / "assets" / "sounds" / "game"
if game_audio.is_dir():
    datas.append((str(game_audio), "assets/sounds/game"))
s2_icon_pack = ROOT / "assets" / "icons" / "s2"
if s2_icon_pack.is_dir():
    datas.append((str(s2_icon_pack), "assets/icons/s2"))
# Bundled X-Ray UI chrome (frames, buttons) for the game-skinned shell.
chrome_pack = ROOT / "assets" / "chrome" / "xray"
if chrome_pack.is_dir():
    datas.append((str(chrome_pack), "assets/chrome/xray"))
# Reference shell textures used by the visible desktop UI.  Keep them as
# ordinary data files so TextureFrame can resolve them beside the bundled UI.
shell_pack = ROOT / "assets" / "ui" / "s2_shell"
if shell_pack.is_dir():
    datas.append((str(shell_pack), "assets/ui/s2_shell"))
glyph_pack = ROOT / "assets" / "ui" / "item_glyphs"
if glyph_pack.is_dir():
    datas.append((str(glyph_pack), "assets/ui/item_glyphs"))
shell_icon_pack = ROOT / "assets" / "ui" / "shell_icons"
if shell_icon_pack.is_dir():
    datas.append((str(shell_icon_pack), "assets/ui/shell_icons"))

font_pack = ROOT / "assets" / "fonts"
if font_pack.is_dir():
    datas.append((str(font_pack), "assets/fonts"))
# Official item names, icons coordinates and upgrades for the trilogy
# (XRayCatalogProvider.load_generated_bundle reads <bundle>/web/catalogs.json)
# when no original installation is found next to the save.
datas.append((str(ROOT / "web" / "catalogs.json"), "web"))
# Official names in 13 languages (editor/official_names.py).
datas.append((str(ROOT / "web" / "catalog_names.json"), "web"))
# S.T.A.L.K.E.R. 2 official names and icons (editor/s2_items.py).
datas.append((str(ROOT / "web" / "s2_items.json"), "web"))
# Interface translations (editor/i18n.py reads <bundle>/locales/<code>.json).
for locale_file in sorted((ROOT / "locales").glob("*.json")):
    if not locale_file.name.startswith("_"):
        datas.append((str(locale_file), "locales"))
provenance_dir = ROOT / "third_party" / "pyooz"
if provenance_dir.is_dir():
    datas.append((str(provenance_dir), "third_party/pyooz"))
# The Linux .so is a compatibility fallback.  Windows must receive its own
# platform pyooz extension from the Windows wheel and never this binary.
if TARGET == "linux" and (ROOT / "vendor").is_dir():
    datas.append((str(ROOT / "vendor"), "vendor"))

hiddenimports = ["ooz"] if importlib.util.find_spec("ooz") is not None else []
if ENCODER_DIR is not None and importlib.util.find_spec("ooz_encoder") is not None:
    hiddenimports.append("ooz_encoder")
pathex = [str(ROOT)]
if ENCODER_DIR is not None:
    pathex.append(str(ENCODER_DIR))

a = Analysis(
    [
        str(ROOT / "packaging" / "gui_entry.py"),
        str(ROOT / "packaging" / "diagnostic.py"),
        str(ROOT / "packaging" / "native_entry.py"),
        str(ROOT / "packaging" / "updater_entry.py"),
    ],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
runtime_scripts = [entry for entry in a.scripts if entry[0].startswith("pyi_rth_")]
def _entry(script_name):
    """Find one analyzed script by file name.

    Matching on "packaging/gui_entry.py" only works where the separator is a
    slash; on Windows PyInstaller reports "packaging\\gui_entry.py" and the
    lookup raised StopIteration in the middle of the build.
    """

    for entry in a.scripts:
        if PurePath(entry[1]).name == script_name:
            return entry
    raise SystemExit(f"spec: analyzed script not found: {script_name}")


gui_entry = _entry("gui_entry.py")
diagnostic_entry = _entry("diagnostic.py")
native_entry = _entry("native_entry.py")
updater_entry = _entry("updater_entry.py")
gui = EXE(
    pyz,
    [*runtime_scripts, gui_entry],
    exclude_binaries=True,
    name="SaveEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
diagnostic = EXE(
    pyz,
    [*runtime_scripts, diagnostic_entry],
    exclude_binaries=True,
    name="SaveEditor-diagnostic",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
native = EXE(
    pyz,
    [*runtime_scripts, native_entry],
    exclude_binaries=True,
    name="SaveEditor-native",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
updater = EXE(
    pyz,
    [*runtime_scripts, updater_entry],
    exclude_binaries=True,
    name="SaveEditor-updater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
COLLECT(
    gui,
    diagnostic,
    native,
    updater,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SaveEditor",
)
