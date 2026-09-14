from __future__ import annotations

import struct

import pytest

import save_format as sf


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


@pytest.fixture(autouse=True)
def _no_qt_thread_outlives_its_test():
    """Never let a test end with a Qt worker thread still running.

    Qt aborts the process when a QThread is destroyed while running, and pytest
    tears widgets down whenever it likes.  The Windows job died exactly that way
    - exit code -1 partway through a module, no traceback and no failed
    assertion.  Waiting here makes the teardown order stop mattering.
    """

    yield

    try:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication
    except ImportError:  # the core environment has no Qt
        return

    app = QApplication.instance()
    if app is None:
        return
    for widget in list(app.topLevelWidgets()):
        for thread in widget.findChildren(QThread):
            if thread.isRunning():
                thread.quit()
                thread.wait(10_000)
    app.processEvents()
