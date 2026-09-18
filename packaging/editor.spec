"""PyInstaller spec for the GUI and a console diagnostic companion."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path, PurePath

from PyInstaller.building.build_main import Analysis, EXE, COLLECT, PYZ


_root_from_env = os.environ.get("SAVE_EDITOR_ROOT")
ROOT = Path(_root_from_env or Path.cwd()).resolve()
TARGET = os.environ.get("SAVE_EDITOR_TARGET", "linux").strip().lower()

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
# Bundled X-Ray UI chrome (frames, buttons) for the game-skinned shell.
chrome_pack = ROOT / "assets" / "chrome" / "xray"
if chrome_pack.is_dir():
    datas.append((str(chrome_pack), "assets/chrome/xray"))
provenance_dir = ROOT / "third_party" / "pyooz"
if provenance_dir.is_dir():
    datas.append((str(provenance_dir), "third_party/pyooz"))
# The Linux .so is a compatibility fallback.  Windows must receive its own
# platform pyooz extension from the Windows wheel and never this binary.
if TARGET == "linux" and (ROOT / "vendor").is_dir():
    datas.append((str(ROOT / "vendor"), "vendor"))

hiddenimports = ["ooz"] if importlib.util.find_spec("ooz") is not None else []

a = Analysis(
    [str(ROOT / "packaging" / "gui_entry.py"), str(ROOT / "packaging" / "diagnostic.py")],
    pathex=[str(ROOT)],
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
COLLECT(
    gui,
    diagnostic,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SaveEditor",
)
