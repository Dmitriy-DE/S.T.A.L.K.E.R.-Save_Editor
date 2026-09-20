"""Backend selection: native first, helper fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from editor.steam_backend import make_cloud_worker
from editor.steam_native import SteamNativeSubprocessWorker
from steam_cloud import SteamCloudError, SteamWorker


class _OkNative:
    def __init__(self, *, log=None):
        self.started = False

    def start(self):
        self.started = True


class _FailNative:
    def __init__(self, *, log=None):
        raise RuntimeError("no libsteam_api")


class _Helper:
    def __init__(self, path, *, log=None):
        self.path = path


def test_native_worker_preferred_when_available():
    worker = make_cloud_worker(Path("/tmp/helper.AppImage"), native_factory=_OkNative,
                               helper_factory=_Helper)
    assert isinstance(worker, _OkNative)
    assert worker.started


def test_fallback_to_helper_when_native_unavailable():
    worker = make_cloud_worker(Path("/tmp/helper.AppImage"), native_factory=_FailNative,
                               helper_factory=_Helper)
    assert isinstance(worker, _Helper)
    assert worker.path == Path("/tmp/helper.AppImage")


def test_no_helper_and_no_native_raises():
    with pytest.raises(SteamCloudError):
        make_cloud_worker(None, native_factory=_FailNative, helper_factory=_Helper)


def test_default_backend_uses_killable_native_transport():
    worker = make_cloud_worker(None, native_factory=None)

    assert isinstance(worker, SteamNativeSubprocessWorker)
    assert worker.write_capability.writable is True
    worker.close()


def test_helper_transport_advertises_writable() -> None:
    worker = SteamWorker(Path("/tmp/helper.AppImage"))

    assert worker.write_capability.writable is True
