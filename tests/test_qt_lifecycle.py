from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


def test_qt_worker_is_stopped_before_pytest_qt_closes_widget(qtbot, request) -> None:
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QWidget

    widget = QWidget()
    worker_thread = QThread(widget)
    worker_thread.start()
    qtbot.waitUntil(worker_thread.isRunning, timeout=1_000)
    # pytest-qt tracks a weak reference; keep the test widget alive until its
    # teardown hook gets a chance to stop the child thread.
    request.node._lifecycle_widget = widget

    def before_close(_widget: QWidget) -> None:
        assert not worker_thread.isRunning()

    qtbot.addWidget(widget, before_close_func=before_close)
