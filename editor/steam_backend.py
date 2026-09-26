"""Create the killable in-project Steam Cloud worker."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .steam_native import SteamNativeSubprocessWorker


def make_cloud_worker(
    *,
    native_factory: Callable[..., Any] | None = None,
    log: Callable[[str], None] | None = None,
) -> Any:
    """Start the native worker; Steam web fallback stays inside that worker."""

    emit = log or (lambda _message: None)
    factory = native_factory
    if factory is None:
        factory = lambda *, log=None: SteamNativeSubprocessWorker(log=log)  # noqa: E731
    worker = factory(log=log)
    worker.start()
    emit("Steam Cloud: native worker готов")
    return worker


__all__ = ["make_cloud_worker"]
