from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")


from editor.models import EditPlan, PreparedEdit, SourceRef
from editor.service import EditorService
from steam_cloud import CloudFile
from ui.cloud_view import CloudView
from ui.main_window import MainWindow

# These cases drive real QThreads end to end.  Five seconds was enough on a
# developer machine and not on a loaded CI runner, where the same test timed out
# while the work was still progressing - a slow machine is not a defect.
SIGNAL_TIMEOUT_MS = 30_000


class FakeCloudTransport:
    def __init__(self, source: bytes, *, files: list[CloudFile] | None = None, persisted: bool = True) -> None:
        self.source = source
        self.files = files or []
        self.persisted = persisted
        self.connected = False
        self.write_calls: list[tuple[str, bytes]] = []
        self.closed = False

    def start(self) -> None:
        return None

    def connect(self, _app_id: int) -> None:
        self.connected = True

    def list_files(self) -> list[CloudFile]:
        return list(self.files)

    def read_file(self, _filename: str) -> bytes:
        if self.write_calls:
            return self.write_calls[-1][1]
        return self.source

    def write_file(self, filename: str, data: bytes) -> None:
        self.write_calls.append((filename, bytes(data)))

    def sync(self) -> None:
        return None

    def wait_persisted(self, _filename: str, _expected_size: int, timeout: int = 120) -> bool:
        assert timeout > 0
        return self.persisted

    def close(self) -> None:
        self.closed = True


def _cloud_file(name: str) -> CloudFile:
    return CloudFile(name=name, size=123, timestamp=1_700_000_000, is_persisted=True, exists=True)


def _prepared(data: bytes, name: str) -> PreparedEdit:
    plan = EditPlan(
        source=SourceRef(
            kind="cloud",
            locator=name,
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        money=900,
    )
    return EditorService().prepare(data, plan)


def test_cloud_view_does_not_start_helper_on_open(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    created: list[FakeCloudTransport] = []

    def factory(_path: Path) -> FakeCloudTransport:
        transport = FakeCloudTransport(synthetic_save)
        created.append(transport)
        return transport

    view = CloudView(
        EditorService(),
        worker_factory=factory,
        helper_path=tmp_path / "helper",
        backup_dir=tmp_path / "backups",
    )
    qtbot.addWidget(view)

    assert created == []
    assert not view.upload_button.isEnabled()
    assert "не подключ" in view.status_label.text().lower()


def test_cloud_view_missing_helper_is_explicit_and_has_no_transport_write(
    qtbot, synthetic_save: bytes
) -> None:
    created: list[FakeCloudTransport] = []
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: created.append(FakeCloudTransport(synthetic_save)) or created[-1],
        helper_finder=lambda: None,
    )
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.operation_failed, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()

    assert created == []
    assert "helper" in view.error_label.text().lower()


def test_cloud_view_empty_list_has_explicit_state(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    transport = FakeCloudTransport(synthetic_save)
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: transport,
        helper_path=tmp_path / "helper",
        backup_dir=tmp_path / "backups",
    )
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()

    assert view.table.rowCount() == 0
    assert "0" in view.status_label.text()
    assert not view.analyze_button.isEnabled()


def test_cloud_view_filters_non_data_files(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    data_name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav"
    transport = FakeCloudTransport(
        synthetic_save,
        files=[
            _cloud_file(data_name),
            _cloud_file("Stalker2/Saved/STEAM/SaveGames/Thumbnails/slot-a.png"),
        ],
    )
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: transport,
        helper_path=tmp_path / "helper",
    )
    qtbot.addWidget(view)
    with qtbot.waitSignal(view.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()

    assert [cloud_file.name for cloud_file in view.files] == [data_name]
    assert view.table.rowCount() == 1


def test_cloud_view_pins_selected_data_path_and_rejects_wrong_slot(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav"
    transport = FakeCloudTransport(synthetic_save, files=[_cloud_file(name)])
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: transport,
        helper_path=tmp_path / "helper",
        backup_dir=tmp_path / "backups",
    )
    qtbot.addWidget(view)
    with qtbot.waitSignal(view.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()
    qtbot.waitUntil(lambda: not view.is_busy, timeout=SIGNAL_TIMEOUT_MS)
    view.table.selectRow(0)
    with qtbot.waitSignal(view.snapshot_ready, timeout=SIGNAL_TIMEOUT_MS) as blocker:
        view.analyze_selected()
    qtbot.waitUntil(lambda: not view.is_busy, timeout=SIGNAL_TIMEOUT_MS)

    snapshot = blocker.args[0]
    assert snapshot.name == name
    assert snapshot.info.sha256 == hashlib.sha256(synthetic_save).hexdigest()

    wrong = _prepared(synthetic_save, "Stalker2/Saved/STEAM/SaveGames/Data/slot-b.sav")
    view.set_prepared(wrong)
    assert not view.upload_button.isEnabled()
    with qtbot.waitSignal(view.operation_failed, timeout=SIGNAL_TIMEOUT_MS):
        view.start_upload()
    assert transport.write_calls == []


@pytest.mark.parametrize("persisted", [True, False])
def test_cloud_view_upload_reports_verified_or_uncertain_without_retry(
    qtbot, synthetic_save: bytes, tmp_path: Path, persisted: bool
) -> None:
    name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav"
    transport = FakeCloudTransport(
        synthetic_save,
        files=[_cloud_file(name)],
        persisted=persisted,
    )
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: transport,
        helper_path=tmp_path / "helper",
        backup_dir=tmp_path / "backups",
    )
    qtbot.addWidget(view)
    with qtbot.waitSignal(view.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()
    qtbot.waitUntil(lambda: not view.is_busy, timeout=SIGNAL_TIMEOUT_MS)
    view.table.selectRow(0)
    with qtbot.waitSignal(view.snapshot_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.analyze_selected()
    qtbot.waitUntil(lambda: not view.is_busy, timeout=SIGNAL_TIMEOUT_MS)
    view.set_prepared(_prepared(synthetic_save, name))

    with qtbot.waitSignal(view.upload_ready, timeout=SIGNAL_TIMEOUT_MS) as blocker:
        view.start_upload()

    receipt = blocker.args[0]
    assert receipt.status == ("verified" if persisted else "uncertain")
    assert len(transport.write_calls) == 1
    assert view.upload_button.isEnabled() is False
    if persisted:
        assert "verified" in view.result_label.text().lower()
    else:
        assert "uncertain" in view.result_label.text().lower()


def test_main_window_routes_cloud_snapshot_preview_to_upload(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav"
    transport = FakeCloudTransport(synthetic_save, files=[_cloud_file(name)])
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    window.cloud_view.worker_factory = lambda _path: transport
    window.cloud_view.helper_path = tmp_path / "helper"
    window.cloud_view.helper_edit.setText(str(tmp_path / "helper"))
    window.cloud_view.backup_dir = tmp_path / "backups"

    with qtbot.waitSignal(window.cloud_view.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        window.cloud_view.start_connect()
    qtbot.waitUntil(lambda: not window.cloud_view.is_busy, timeout=SIGNAL_TIMEOUT_MS)
    window.cloud_view.table.selectRow(0)
    with qtbot.waitSignal(window.cloud_view.snapshot_ready, timeout=SIGNAL_TIMEOUT_MS):
        window.cloud_view.analyze_selected()

    assert window.snapshot is not None
    assert window.snapshot.source_kind == "cloud"
    assert window.snapshot.locator == name

    # snapshot_ready fires from inside the cloud worker; the thread is still
    # running for a moment afterwards, and preview refuses to start while the
    # window is busy.  On a fast machine that window is too short to notice.
    qtbot.waitUntil(lambda: not window._cloud_busy, timeout=SIGNAL_TIMEOUT_MS)

    window.money_spin.setValue(900)
    window._stage_money()
    with qtbot.waitSignal(window.preview_ready, timeout=SIGNAL_TIMEOUT_MS):
        window._start_preview()
    with qtbot.waitSignal(window.apply_ready, timeout=SIGNAL_TIMEOUT_MS) as blocker:
        window._start_cloud_upload()

    assert blocker.args[0].status == "verified"
    assert [filename for filename, _data in transport.write_calls] == [name]


def test_closing_the_view_waits_for_its_worker(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    """Qt aborts the process if a QThread is destroyed while still running.

    The Windows job died with exit code -1 in the middle of this module, with no
    traceback - the shape of that abort rather than a failed assertion.
    """

    transport = FakeCloudTransport(synthetic_save, files=[_cloud_file("Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav")])
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: transport,
        helper_path=tmp_path / "helper",
        backup_dir=tmp_path / "backups",
    )
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()

    view.close()

    assert view._thread is None or not view._thread.isRunning()
    assert view.transport is None
