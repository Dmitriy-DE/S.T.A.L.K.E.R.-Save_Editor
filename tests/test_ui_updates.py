from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from editor.service import EditorService
from editor.update_manifest import ArtifactSpec
from editor.updater import InstallationInfo, UpdateCheckResult
from ui.main_window import MainWindow
from ui.update_dialog import UpdateCheckWorker, UpdateDialog


def _artifact(kind: str = "portable") -> ArtifactSpec:
    if kind == "installer":
        target = "windows-installer-x86_64"
        file = "SaveEditor-windows-x86_64-setup.exe"
    elif kind == "package":
        target = "linux-deb-amd64"
        file = "stalker2-save-editor_amd64.deb"
    else:
        target = "windows-x86_64"
        file = "SaveEditor-windows-x86_64.zip"
    return ArtifactSpec(
        target=target,
        architecture="x86_64",
        kind=kind,
        file=file,
        size=4,
        sha256=hashlib.sha256(b"test").hexdigest(),
        url="https://save-editor-downloads.save-editor.workers.dev/update.zip",
    )


class _FakeClient:
    def __init__(self, result: UpdateCheckResult) -> None:
        self.result = result
        self.calls = 0

    def check(self) -> UpdateCheckResult:
        self.calls += 1
        return self.result


def _installation(tmp_path: Path) -> InstallationInfo:
    root = tmp_path / "SaveEditor"
    root.mkdir(exist_ok=True)
    executable = root / "SaveEditor.exe"
    executable.write_bytes(b"app")
    return InstallationInfo("windows", "x86_64", "portable", root, executable)


def test_update_check_worker_runs_client_and_emits_result(qtbot) -> None:
    expected = UpdateCheckResult("current")
    client = _FakeClient(expected)
    worker = UpdateCheckWorker(client)

    with qtbot.waitSignal(worker.result, timeout=1_000) as blocker:
        worker.start()
    worker.wait(1_000)

    assert blocker.args == [expected]
    assert client.calls == 1


def test_update_dialog_explains_current_and_available_states(qtbot, tmp_path: Path) -> None:
    current = UpdateDialog(UpdateCheckResult("current"), installation=_installation(tmp_path))
    qtbot.addWidget(current)
    assert "актуальна" in current.status_label.text().casefold()
    assert not current.download_button.isEnabled()

    available = UpdateDialog(
        UpdateCheckResult("available", artifact=_artifact()),
        installation=_installation(tmp_path),
        client=_FakeClient(UpdateCheckResult("available", artifact=_artifact())),
    )
    qtbot.addWidget(available)
    assert "обновление" in available.status_label.text().casefold()
    assert available.download_button.isEnabled()

    installer = UpdateDialog(
        UpdateCheckResult("available", artifact=_artifact("installer")),
        installation=_installation(tmp_path),
        client=_FakeClient(UpdateCheckResult("available", artifact=_artifact("installer"))),
    )
    qtbot.addWidget(installer)
    installer._on_downloaded(tmp_path / "setup.exe")
    assert installer.restart_button.text() == "Открыть установщик"


def test_main_window_manual_check_uses_injected_client(qtbot, tmp_path: Path) -> None:
    client = _FakeClient(UpdateCheckResult("current"))
    window = MainWindow(
        EditorService(),
        update_client=client,
        auto_update_check=False,
    )
    qtbot.addWidget(window)

    window.check_for_updates(manual=True)
    qtbot.waitUntil(lambda: client.calls == 1, timeout=1_000)
    qtbot.waitUntil(lambda: window._update_dialog is not None, timeout=1_000)
    assert window._update_dialog.status_label.text()
