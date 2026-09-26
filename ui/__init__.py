"""Optional Qt user interface for the save editor.

Names are imported on first use: helper child processes start as
``python -m ui --peek|--steam-native-op|--extract-game-audio`` and must not
load the whole Qt window stack just to parse one file (PERF-1).
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "BackupController": ".backup_controller",
    "RestoreWorker": ".backup_controller",
    "CloudController": ".cloud_controller",
    "CloudOperationWorker": ".cloud_controller",
    "CloudSnapshot": ".cloud_controller",
    "InventoryTableModel": ".inventory_model",
    "LocalSnapshot": ".main_window",
    "MainWindow": ".main_window",
    "OperationWorker": ".operation_worker",
}


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module 'ui' has no attribute {name!r}")
    value = getattr(import_module(module, __name__), name)
    globals()[name] = value
    return value


__all__ = sorted(_EXPORTS)
