"""Select the Steam Cloud worker: in-process native first, helper fallback.

The Cloud tab injects :func:`make_cloud_worker` as its ``worker_factory``.  We
try the in-project :class:`~editor.steam_native.SteamNativeWorker` (ctypes over
``libsteam_api``) and, only if it cannot initialise — missing library, no
running Steam client, app not owned — fall back to the proven subprocess
helper (:class:`steam_cloud.SteamWorker`), which now auto-extracts its AppImage
without FUSE.  This guarantees the release never ships a dead Cloud tab even
though the native path cannot be verified live in the build session.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from steam_cloud import SteamWorker

from .steam_native import SteamNativeWorker

LOGGER = logging.getLogger(__name__)


def make_cloud_worker(
    helper_path: Path | None,
    *,
    native_factory: Callable[..., Any] = SteamNativeWorker,
    helper_factory: Callable[..., Any] = SteamWorker,
    log: Callable[[str], None] | None = None,
) -> Any:
    """Return a started native worker, or a helper worker as fallback."""

    emit = log or (lambda _s: None)
    try:
        worker = native_factory(log=log)
        worker.start()
        emit("Steam Cloud: нативный worker (libsteam_api) запущен")
        return worker
    except Exception as exc:
        LOGGER.info("Native Steam worker unavailable, falling back to helper: %s", exc)
        if helper_path is None:
            from steam_cloud import SteamCloudError

            raise SteamCloudError(
                "Steam Cloud недоступен: нативный worker не поднялся и "
                f"SteamCloudFileManager не найден ({exc})"
            ) from exc
        emit(f"Steam Cloud: нативный worker недоступен ({exc}); использую helper")
        return helper_factory(helper_path, log=log)


__all__ = ["make_cloud_worker"]
