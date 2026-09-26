"""Every application and Cloud entry point must import without starting Steam."""

from __future__ import annotations

import importlib

import pytest

CORE_MODULES = ("save_format", "steam_cloud", "cli", "editor", "editor.platforms")
QT_MODULES = (
    "ui",
    "ui.theme",
    "ui.cloud_controller",
    "ui.cloud_library_view",
    "ui.main_window",
)


@pytest.mark.parametrize("name", CORE_MODULES)
def test_core_module_imports(name: str) -> None:
    assert importlib.import_module(name) is not None


@pytest.mark.parametrize("name", QT_MODULES)
def test_qt_module_imports(name: str) -> None:
    pytest.importorskip("PySide6")
    assert importlib.import_module(name) is not None
