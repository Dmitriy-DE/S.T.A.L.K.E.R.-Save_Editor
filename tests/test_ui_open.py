from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from editor.service import EditorService
from ui.main_window import MainWindow


def test_local_open_is_async_and_populates_summary(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    source = tmp_path / "локальный сейв.sav"
    source.write_bytes(synthetic_save)
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    assert not window.edit_actions_enabled
    with qtbot.waitSignal(window.analysis_ready, timeout=5_000):
        window._start_inspect(source)

    assert window.edit_actions_enabled
    assert window.snapshot is not None
    assert window.snapshot.path == source
    assert source.name in window.editor_view.breadcrumb.text()
    assert "CRC PASS" in window.editor_view.integrity_label.text()
    assert "100" in window.editor_view.money_label.text()
    assert window.snapshot.format_id == "stalker2"
    assert window.snapshot.format_title == "S.T.A.L.K.E.R. 2: Heart of Chornobyl"


def test_malformed_open_keeps_previous_snapshot(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    source = tmp_path / "valid.sav"
    source.write_bytes(synthetic_save)
    malformed = tmp_path / "broken.sav"
    malformed.write_bytes(b"broken")
    window = MainWindow(EditorService())
    qtbot.addWidget(window)

    with qtbot.waitSignal(window.analysis_ready, timeout=5_000):
        window._start_inspect(source)
    qtbot.waitUntil(window.open_button.isEnabled, timeout=5_000)
    previous_snapshot = window.snapshot
    previous_breadcrumb = window.editor_view.breadcrumb.text()

    with qtbot.waitSignal(window.analysis_failed, timeout=5_000):
        window._start_inspect(malformed)

    assert window.snapshot is previous_snapshot
    assert window.editor_view.breadcrumb.text() == previous_breadcrumb
    assert "broken.sav" in window.error_label.text()
    assert window.edit_actions_enabled


def test_unknown_format_uses_the_core_error_message(
    qtbot, tmp_path: Path
) -> None:
    from editor.formats import FormatDetectionError

    data = b"plain text that is not a save"
    path = tmp_path / "wrong-name.sav"
    path.write_bytes(data)
    with pytest.raises(FormatDetectionError) as caught:
        EditorService().inspect(data, source_name=path.name)
    expected = str(caught.value)

    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    with qtbot.waitSignal(window.analysis_failed, timeout=5_000):
        window._start_inspect(path)

    assert window.error_label.text() == expected
    assert path.read_bytes() == data
