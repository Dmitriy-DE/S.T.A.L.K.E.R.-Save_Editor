"""Select the Steam Cloud worker: killable native child first, helper fallback.

The Cloud tab injects :func:`make_cloud_worker` as its ``worker_factory``.  We
try the in-project :class:`~editor.steam_native.SteamNativeSubprocessWorker`,
which keeps the uninterruptible ``ctypes`` calls in a killable child process.
If its initial native list cannot complete, it falls back to the proven
subprocess helper (:class:`steam_cloud.SteamWorker`), which now auto-extracts
its AppImage without FUSE.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from steam_cloud import SteamWorker

from .steam_native import SteamNativeSubprocessWorker

LOGGER = logging.getLogger(__name__)


def make_cloud_worker(
    helper_path: Path | None,
    *,
    native_factory: Callable[..., Any] | None = None,
    helper_factory: Callable[..., Any] = SteamWorker,
    log: Callable[[str], None] | None = None,
) -> Any:
    """Return a killable native worker, or a helper worker as fallback."""

    emit = log or (lambda _s: None)
    factory = native_factory
    if factory is None:
        factory = lambda *, log=None: SteamNativeSubprocessWorker(  # noqa: E731
            helper_path=helper_path,
            helper_factory=helper_factory,
            log=log,
        )
    try:
        worker = factory(log=log)
        worker.start()
        emit("Steam Cloud: killable native worker готов")
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
