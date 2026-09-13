"""PyInstaller spec for the GUI and a console diagnostic companion."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

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
gui_entry = next(entry for entry in a.scripts if entry[1].endswith("packaging/gui_entry.py"))
diagnostic_entry = next(entry for entry in a.scripts if entry[1].endswith("packaging/diagnostic.py"))
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
