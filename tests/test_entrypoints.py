"""Every entry point must import cleanly.

`app.py` and `ui/cloud_view.py` import `discover_helper` from `steam_cloud`,
which only re-exports it from `editor.platforms`.  Nothing in the suite used to
import those modules, so a broken re-export stayed green while both GUIs failed
on startup.  These tests close that gap: they only import, they never build a
window or contact Steam.
"""

from __future__ import annotations

import importlib

import pytest

CORE_MODULES = ("save_format", "steam_cloud", "cli", "editor", "editor.platforms")
QT_MODULES = ("ui", "ui.theme", "ui.cloud_view", "ui.main_window")


@pytest.mark.parametrize("name", CORE_MODULES)
def test_core_module_imports(name: str) -> None:
    assert importlib.import_module(name) is not None


def test_tk_application_imports() -> None:
    pytest.importorskip("tkinter")
    module = importlib.import_module("app")
    assert hasattr(module, "App")


@pytest.mark.parametrize("name", QT_MODULES)
def test_qt_module_imports(name: str) -> None:
    pytest.importorskip("PySide6")
    assert importlib.import_module(name) is not None


def test_steam_cloud_reexports_helper_discovery() -> None:
    import steam_cloud
    from editor.platforms import discover_helper

    assert steam_cloud.discover_helper is discover_helper
    assert "discover_helper" in steam_cloud.__all__
