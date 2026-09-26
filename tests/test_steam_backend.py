"""The Cloud worker factory starts only the in-project native transport."""

from __future__ import annotations

import pytest

from editor.steam_backend import make_cloud_worker
from editor.steam_native import SteamNativeSubprocessWorker


class _OkNative:
    def __init__(self, *, log=None):
        self.started = False

    def start(self):
        self.started = True


class _FailNative:
    def __init__(self, *, log=None):
        raise RuntimeError("no libsteam_api")


def test_native_worker_is_started_and_returned() -> None:
    worker = make_cloud_worker(native_factory=_OkNative)

    assert isinstance(worker, _OkNative)
    assert worker.started


def test_native_start_failure_is_not_hidden_by_another_transport() -> None:
    with pytest.raises(RuntimeError, match="no libsteam_api"):
        make_cloud_worker(native_factory=_FailNative)


def test_default_backend_uses_killable_native_transport() -> None:
    worker = make_cloud_worker()

    assert isinstance(worker, SteamNativeSubprocessWorker)
    assert worker.write_capability.writable is True
    worker.close()
