from __future__ import annotations

import hashlib
import threading
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QMessageBox

from editor.capabilities import CapabilitySupport, FormatCapabilities
from editor.cloud_capabilities import CloudWriteCapability
from editor.formats import FormatInspection
from editor.models import EditPlan, PreparedEdit, SourceRef
from editor.service import EditorService
from steam_cloud import CloudFile
from ui.cloud_controller import CloudController, CloudOperationWorker
from ui.cloud_library_view import CloudLibraryView
from ui.diagnostics_dialog import DiagnosticsDialog
from ui.main_window import MainWindow

# These cases drive real QThreads end to end.  Five seconds was enough on a
# developer machine and not on a loaded CI runner, where the same test timed out
# while the work was still progressing - a slow machine is not a defect.
SIGNAL_TIMEOUT_MS = 30_000


class CloudSurface(CloudLibraryView):
    """Test harness joining canonical presentation and backend state."""

    _ALIASES: ClassVar[dict[str, str]] = {
        "table": "save_table",
        "analyze_button": "download_button",
        "status_label": "status_chip",
        "intro_label": "read_only_banner",
    }

    def __init__(self, *args, **kwargs) -> None:
        backend = CloudController(*args, **kwargs)
        super().__init__(backend)
        object.__setattr__(self, "_backend", backend)

    def __getattr__(self, name: str):
        alias = self._ALIASES.get(name)
        if alias is not None:
            return getattr(self, alias)
        backend = object.__getattribute__(self, "_backend")
        return getattr(backend, name)

    def __setattr__(self, name: str, value) -> None:
        if name not in {"_backend", "backend"} and "_backend" in self.__dict__:
            backend = object.__getattribute__(self, "_backend")
            if name in {"service", "worker_factory", "helper_finder", "helper_path", "backup_dir"}:
                setattr(backend, name, value)
                return
        super().__setattr__(name, value)


CloudView = CloudSurface


class _ApprovedCloudService(EditorService):
    """Keep this routing test independent from the M10 release gate."""

    def inspect_result(
        self,
        data: bytes,
        *,
        with_inventory: bool = True,
        source_name: str | None = None,
        catalog_source: str | Path | None = None,
    ) -> FormatInspection:
        result = super().inspect_result(
            data,
            with_inventory=with_inventory,
            source_name=source_name,
            catalog_source=catalog_source,
        )
        return replace(
            result,
            capabilities=FormatCapabilities(
                read_inventory=True,
                mutation_support={
                    "edit_money": CapabilitySupport("experimental"),
                    "edit_stacks": CapabilitySupport("experimental"),
                },
            ),
        )


def _wait_cloud_idle(qtbot, view: CloudView) -> None:
    """Wait for both the worker thread and its owner reference to settle."""

    qtbot.waitUntil(
        lambda: not view.is_busy and view._thread is None,
        timeout=SIGNAL_TIMEOUT_MS,
    )


class FakeCloudTransport:
    def __init__(
        self,
        source: bytes,
        *,
        files: list[CloudFile] | None = None,
        persisted: bool = True,
        writable: bool = True,
    ) -> None:
        self.source = source
        self.files = files or []
        self.persisted = persisted
        self.connected = False
        self.write_calls: list[tuple[str, bytes]] = []
        self.closed = False
        self.write_capability = CloudWriteCapability(
            writable,
            "fake writer ready" if writable else "Steam web read-only",
        )

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


class BlockingCloudTransport(FakeCloudTransport):
    def __init__(self, source: bytes) -> None:
        super().__init__(source)
        self.started = threading.Event()
        self.released = threading.Event()

    def list_files(self) -> list[CloudFile]:
        self.started.set()
        self.released.wait(5)
        return list(self.files)

    def close(self) -> None:
        super().close()
        self.released.set()


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


def test_diagnostics_dialog_previews_before_sending_and_reports_success(
    qtbot, monkeypatch
) -> None:
    started = threading.Event()

    def fake_submit_logs() -> str:
        started.set()
        return "report-123"

    monkeypatch.setattr("ui.diagnostics_dialog.submit_logs", fake_submit_logs)
    dialog = DiagnosticsDialog()
    qtbot.addWidget(dialog)

    dialog._send()

    assert started.wait(2)
    qtbot.waitUntil(lambda: dialog._worker is None, timeout=SIGNAL_TIMEOUT_MS)
    assert "Обезличенный архив подготовлен" in dialog.preview_label.text()
    assert "report-123" in dialog.status_label.text()


def test_diagnostics_dialog_exports_in_a_worker_and_keeps_send_available(
    qtbot, monkeypatch, tmp_path: Path
) -> None:
    export_path = tmp_path / "diagnostics.log.gz"
    monkeypatch.setattr(
        "ui.diagnostics_dialog.QFileDialog.getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(export_path), "Gzip logs (*.log.gz)")),
    )
    monkeypatch.setattr(
        "ui.diagnostics_dialog.export_log_bundle",
        lambda destination: Path(destination).write_bytes(b"redacted") or Path(destination),
    )
    dialog = DiagnosticsDialog()
    qtbot.addWidget(dialog)

    dialog._export()

    qtbot.waitUntil(lambda: dialog._export_worker is None, timeout=SIGNAL_TIMEOUT_MS)
    assert export_path.read_bytes() == b"redacted"
    assert dialog.send_button.isEnabled()


def test_cloud_view_does_not_connect_on_construction(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
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

    # Mere construction never connects; the auto-connect fires on showEvent.
    assert created == []
    assert not view.upload_button.isEnabled()


def test_cloud_intro_describes_one_click_save_and_read_only_boundary(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: FakeCloudTransport(synthetic_save, writable=False),
        backup_dir=tmp_path / "backups",
    )
    qtbot.addWidget(view)

    assert "только после проверки" in view.intro_label.text().casefold()
    assert "твоего подтверждения" in view.intro_label.text().casefold()
    assert "Загрузить в облако" not in view.intro_label.text()


def test_cloud_view_connects_without_a_helper(qtbot, synthetic_save: bytes, tmp_path: Path) -> None:
    # The native worker needs no AppImage, so an absent helper must not block a
    # connect — this is what lets the tab auto-connect in the background.
    transport = FakeCloudTransport(synthetic_save)
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: transport,
        helper_finder=lambda: None,
        backup_dir=tmp_path / "backups",
    )
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()

    _wait_cloud_idle(qtbot, view)
    assert view.transport is transport


def test_cloud_view_surfaces_a_connect_failure(qtbot, tmp_path: Path) -> None:
    def failing_factory(_path: Path) -> FakeCloudTransport:
        raise RuntimeError("no cloud backend")

    view = CloudView(
        EditorService(),
        worker_factory=failing_factory,
        helper_finder=lambda: None,
        backup_dir=tmp_path / "backups",
    )
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.operation_failed, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()

    _wait_cloud_idle(qtbot, view)
    assert view.transport is None


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

    _wait_cloud_idle(qtbot, view)
    assert view.table.rowCount() == 0
    assert view.status_label.text() == "ПОДКЛЮЧЕНО"
    assert view.detail_name.text() == "Подходящие сохранения не найдены"
    assert view.detail_meta.text() == "В выбранном профиле нет доступных сохранений."
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

    _wait_cloud_idle(qtbot, view)
    assert [cloud_file.name for cloud_file in view.files] == [data_name]
    assert view.table.rowCount() == 1
    assert view.table.columnCount() == 5
    assert view.table.item(0, view.SOURCE_COLUMN).text() == "Неизвестно"


def test_cloud_view_hides_editor_artifacts_and_explains_why(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    data_name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav"
    artifact_name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a-edited.sav"
    transport = FakeCloudTransport(
        synthetic_save,
        files=[_cloud_file(data_name), _cloud_file(artifact_name)],
    )
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: transport,
        helper_path=tmp_path / "helper",
    )
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()
    _wait_cloud_idle(qtbot, view)

    assert [cloud_file.name for cloud_file in view.files] == [data_name]
    assert view._hidden_editor_artifacts == 1
    assert view.status_label.text() == "ПОДКЛЮЧЕНО"
    assert "Технические детали:" in view.status_label.toolTip()
    assert "скрыто 1" in view.status_label.toolTip()


def test_cloud_view_profile_switch_filters_the_selected_game_path(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    original_name = "_appdata_/savedgames/slot.scop"
    transport = FakeCloudTransport(
        synthetic_save,
        files=[
            _cloud_file(original_name),
            _cloud_file("Stalker2/Saved/STEAM/SaveGames/Data/slot.sav"),
            _cloud_file("_appdata_/screenshots/slot.png"),
        ],
    )
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: transport,
        helper_path=tmp_path / "helper",
    )
    qtbot.addWidget(view)
    index = view.profile_combo.findData("stalker-cop")
    assert index >= 0
    view.profile_combo.setCurrentIndex(index)
    assert view.profile.release_id == "stalker-cop"
    assert view.app_id == 41700

    with qtbot.waitSignal(view.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.start_connect()
    _wait_cloud_idle(qtbot, view)

    assert [cloud_file.name for cloud_file in view.files] == [original_name]


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
    _wait_cloud_idle(qtbot, view)
    view.table.selectRow(0)
    with qtbot.waitSignal(view.snapshot_ready, timeout=SIGNAL_TIMEOUT_MS) as blocker:
        view.analyze_selected()
    _wait_cloud_idle(qtbot, view)

    snapshot = blocker.args[0]
    assert snapshot.name == name
    assert snapshot.info.sha256 == hashlib.sha256(synthetic_save).hexdigest()

    wrong = _prepared(synthetic_save, "Stalker2/Saved/STEAM/SaveGames/Data/slot-b.sav")
    view.set_prepared(wrong)
    assert not view.upload_button.isEnabled()
    with qtbot.waitSignal(view.operation_failed, timeout=SIGNAL_TIMEOUT_MS):
        view.start_upload()
    assert transport.write_calls == []


def test_cloud_view_keeps_upload_disabled_until_transport_is_writable(
    qtbot,
    synthetic_save: bytes,
    tmp_path: Path,
) -> None:
    name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav"
    transport = FakeCloudTransport(
        synthetic_save,
        files=[_cloud_file(name)],
        writable=False,
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
    _wait_cloud_idle(qtbot, view)
    view.table.selectRow(0)

    prepared = _prepared(synthetic_save, name)
    view.set_prepared(prepared)

    assert not view.upload_button.isEnabled()
    assert view.result_label.text() == "Запись в Steam Cloud сейчас недоступна."

    transport.write_capability = CloudWriteCapability(True, "native writer ready")
    view.set_prepared(prepared)

    assert view.upload_button.isEnabled()


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
    _wait_cloud_idle(qtbot, view)
    view.table.selectRow(0)
    with qtbot.waitSignal(view.snapshot_ready, timeout=SIGNAL_TIMEOUT_MS):
        view.analyze_selected()
    _wait_cloud_idle(qtbot, view)
    view.set_prepared(_prepared(synthetic_save, name))

    with qtbot.waitSignal(view.upload_ready, timeout=SIGNAL_TIMEOUT_MS) as blocker:
        view.start_upload()

    # ``upload_ready`` is emitted by the worker's ``completed`` signal; the
    # QThread still needs one event-loop turn to emit ``finished`` and clear
    # the widget-owned worker reference.  Wait for that lifecycle boundary
    # before pytest-qt tears the widget down (Windows is particularly strict
    # about destroying a running QThread).
    _wait_cloud_idle(qtbot, view)
    receipt = blocker.args[0]
    assert receipt.status == ("verified" if persisted else "uncertain")
    assert len(transport.write_calls) == 1
    assert view.upload_button.isEnabled() is False
    if persisted:
        assert view.result_label.text() == "Запись успешно проверена."
    else:
        assert view.result_label.text() == (
            "Неясно, записались ли изменения. Мы не будем повторять запись автоматически."
        )


def test_cloud_upload_log_contains_target_size_and_result(
    synthetic_save: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav"
    transport = FakeCloudTransport(synthetic_save, files=[_cloud_file(name)])
    prepared = _prepared(synthetic_save, name)
    from ui import cloud_controller
    worker = CloudOperationWorker(
        EditorService(),
        mode="upload",
        transport=transport,
        prepared=prepared,
        backup_dir=tmp_path / "backups",
    )

    records: list[str] = []

    def record(message: str, *args: object, **_kwargs: object) -> None:
        records.append(message % args if args else message)

    monkeypatch.setattr(cloud_controller.LOGGER, "info", record)
    worker.run()

    text = "\n".join(records)
    assert f"path={name}" in text
    assert f"expected_bytes={len(prepared.data)}" in text
    assert "mode=upload" in text
    assert "status=verified" in text
    assert f"sha256={prepared.output_sha256}" in text


def test_main_window_routes_cloud_snapshot_preview_to_upload(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav"
    transport = FakeCloudTransport(synthetic_save, files=[_cloud_file(name)])
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    # The production registry stays read-only until M10 game evidence.  Use a
    # scoped approved cloud service so this test can still cover the cloud
    # preview/upload transaction without re-rendering the live window.
    window.cloud_controller.service = _ApprovedCloudService()
    window.cloud_controller.worker_factory = lambda _path: transport
    window.cloud_controller.helper_path = tmp_path / "helper"
    window.cloud_controller.backup_dir = tmp_path / "backups"

    with qtbot.waitSignal(window.cloud_controller.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        window.cloud_controller.start_connect()
    qtbot.waitUntil(
        lambda: not window.cloud_controller.is_busy and window.cloud_controller._thread is None,
        timeout=SIGNAL_TIMEOUT_MS,
    )
    window.cloud_reference_view.save_table.selectRow(0)
    with qtbot.waitSignal(window.cloud_controller.snapshot_ready, timeout=SIGNAL_TIMEOUT_MS):
        window.cloud_controller.analyze_selected()

    assert window.snapshot is not None
    assert window.snapshot.source_kind == "cloud"
    assert window.snapshot.locator == name

    # snapshot_ready fires from inside the cloud worker; the thread is still
    # running for a moment afterwards, and preview refuses to start while the
    # window is busy.  On a fast machine that window is too short to notice.
    qtbot.waitUntil(
        lambda: not window._cloud_busy and window.cloud_controller._thread is None,
        timeout=SIGNAL_TIMEOUT_MS,
    )

    window.editor_view.money_spin.setValue(900)
    window._stage_money()
    with qtbot.waitSignal(window.preview_ready, timeout=SIGNAL_TIMEOUT_MS):
        window._start_preview()
    with qtbot.waitSignal(window.apply_ready, timeout=SIGNAL_TIMEOUT_MS) as blocker:
        window._start_cloud_upload()

    qtbot.waitUntil(
        lambda: not window.cloud_controller.is_busy and window.cloud_controller._thread is None,
        timeout=SIGNAL_TIMEOUT_MS,
    )
    assert blocker.args[0].status == "verified"
    assert [filename for filename, _data in transport.write_calls] == [name]


def test_main_window_one_click_save_uploads_cloud_snapshot(
    qtbot, synthetic_save: bytes, tmp_path: Path, monkeypatch
) -> None:
    name = "Stalker2/Saved/STEAM/SaveGames/Data/slot-a.sav"
    transport = FakeCloudTransport(synthetic_save, files=[_cloud_file(name)])
    window = MainWindow(EditorService())
    qtbot.addWidget(window)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes),
    )
    window.cloud_controller.service = _ApprovedCloudService()
    window.cloud_controller.worker_factory = lambda _path: transport
    window.cloud_controller.backup_dir = tmp_path / "backups"

    with qtbot.waitSignal(window.cloud_controller.files_ready, timeout=SIGNAL_TIMEOUT_MS):
        window.cloud_controller.start_connect()
    qtbot.waitUntil(
        lambda: not window.cloud_controller.is_busy and window.cloud_controller._thread is None,
        timeout=SIGNAL_TIMEOUT_MS,
    )
    window.cloud_reference_view.save_table.selectRow(0)
    with qtbot.waitSignal(window.cloud_controller.snapshot_ready, timeout=SIGNAL_TIMEOUT_MS):
        window.cloud_controller.analyze_selected()
    qtbot.waitUntil(
        lambda: not window.cloud_controller.is_busy and window.cloud_controller._thread is None,
        timeout=SIGNAL_TIMEOUT_MS,
    )

    window.editor_view.money_spin.setValue(900)
    window._stage_money()
    with qtbot.waitSignal(window.apply_ready, timeout=SIGNAL_TIMEOUT_MS) as blocker:
        window._save_one_click()

    qtbot.waitUntil(
        lambda: not window.cloud_controller.is_busy and window.cloud_controller._thread is None,
        timeout=SIGNAL_TIMEOUT_MS,
    )
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


def test_closing_the_view_cancels_a_blocking_cloud_worker(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    transport = BlockingCloudTransport(synthetic_save)
    view = CloudView(
        EditorService(),
        worker_factory=lambda _path: transport,
        helper_finder=lambda: None,
        backup_dir=tmp_path / "backups",
    )
    qtbot.addWidget(view)
    view.start_connect()

    assert transport.started.wait(1)
    view.close()
    qtbot.waitUntil(lambda: not view.is_busy, timeout=2_000)

    assert transport.closed is True
    assert view._thread is None or not view._thread.isRunning()
