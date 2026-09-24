from __future__ import annotations

import os
import struct
import tempfile
from pathlib import Path

import pytest

import save_format as sf

_ISOLATED_ENV_KEYS = (
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
)


def pytest_configure(config: pytest.Config) -> None:
    """Run every test against an empty, disposable user profile.

    Without this the UI suite read the developer's real saves, settings,
    backups and diagnostics log.  A test that passed only because that log
    existed hung CI forever on the "journal is empty" message box.
    """

    del config
    profile = Path(tempfile.mkdtemp(prefix="save-editor-test-home-"))
    for key in _ISOLATED_ENV_KEYS:
        target = profile / key.casefold()
        target.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(target)


@pytest.fixture(autouse=True)
def _no_external_applications(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a test launch an app or block on a modal message box.

    Static ``QMessageBox`` helpers run a nested event loop that waits for a
    human; headless CI then hangs until the job timeout.  Tests that need a
    specific answer still monkeypatch these helpers themselves.
    """

    try:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QMessageBox
    except ImportError:  # the core environment has no Qt
        return
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda _url: True))
    no = QMessageBox.StandardButton.No
    ok = QMessageBox.StandardButton.Ok
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *_a, **_k: no))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *_a, **_k: no))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *_a, **_k: ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *_a, **_k: ok))


def _object_record(
    handle: int,
    *,
    x: int,
    y: int,
    count: int,
    total_weight: float,
    kind: int,
    type_key: bytes,
) -> bytes:
    """Build one intentionally small record for synthetic parser tests.

    The layout mirrors only the fields that the current parser reads. It is a
    test fixture, not a claim that this is a complete game object record.
    """
    if len(type_key) != 3:
        raise ValueError("synthetic type_key must be exactly three bytes")
    record = bytearray(64)
    struct.pack_into("<I", record, 0, handle)
    record[8:11] = type_key
    struct.pack_into("<H", record, sf.OBJ_POS_X_OFFSET, x)
    struct.pack_into("<H", record, sf.OBJ_POS_Y_OFFSET, y)
    record[sf.STACK_MARKER_OFFSET] = 0x38
    struct.pack_into("<I", record, sf.STACK_COUNT_OFFSET, count)
    struct.pack_into("<f", record, sf.STACK_WEIGHT_OFFSET, total_weight)
    record[sf.STACK_KIND_OFFSET] = kind
    return bytes(record)


@pytest.fixture
def synthetic_save() -> bytes:
    """Return a private-data-free, valid synthetic save container.

    It contains four owned handles, two visible one-cell objects, and two
    orphan records. The fixture exercises the parser contract only; it does
    not represent a complete or universal STALKER 2 object graph.
    """
    handles = (0x30000001, 0x30000002, 0x30000003, 0x30000004)
    raw = bytearray(b"SYNTHETIC-FIXTURE\x00")
    raw += sf.MONEY_ANCHOR
    raw += struct.pack("<IIH", 100, 1, len(handles))
    raw += struct.pack("<4I", *handles)
    raw += struct.pack("<H", 2)
    raw += struct.pack("<IHH", handles[0], 0, 0)
    raw += struct.pack("<IHH", handles[1], 1, 0)
    raw += _object_record(
        handles[0],
        x=0,
        y=0,
        count=2,
        total_weight=0.2,
        kind=4,
        type_key=b"\x01\x02\x03",
    )
    raw += _object_record(
        handles[1],
        x=1,
        y=0,
        count=1,
        total_weight=0.4,
        kind=5,
        type_key=b"\x04\x05\x06",
    )
    raw += _object_record(
        handles[2],
        x=0xFFFF,
        y=0xFFFF,
        count=1,
        total_weight=0.0,
        kind=0,
        type_key=b"\x07\x08\x09",
    )
    raw += _object_record(
        handles[3],
        x=0xFFFF,
        y=0xFFFF,
        count=1,
        total_weight=0.0,
        kind=99,
        type_key=b"\x0A\x0B\x0C",
    )
    return sf.rebuild_uncompressed(bytes(raw))


def _wait_for_qt_threads(item: pytest.Item) -> None:
    """Stop worker threads before pytest-qt destroys their parent widgets."""
    try:
        from PySide6.QtCore import QThread
    except ImportError:  # the core environment has no Qt
        return

    widgets = getattr(item, "qt_widgets", None)
    if not widgets:
        return
    for widget_ref, _before_close_func in widgets:
        widget = widget_ref()
        if widget is None:
            continue
        for thread in widget.findChildren(QThread):
            if thread.isRunning():
                thread.quit()
                thread.wait(10_000)


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item):
    """Keep Qt workers alive until they can be stopped safely.

    This hook is the outermost teardown wrapper, so it runs before pytest-qt's
    own ``trylast`` wrapper closes and deletes the widgets in ``item``.
    """

    _wait_for_qt_threads(item)
    result = yield
    return result
