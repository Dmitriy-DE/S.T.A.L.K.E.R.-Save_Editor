from __future__ import annotations

import sys

from ui.worker_process import self_command


def test_frozen_macos_read_only_jobs_relaunch_the_app_executable(
    monkeypatch, tmp_path
) -> None:
    app_executable = (
        tmp_path / "SaveEditor.app" / "Contents" / "MacOS" / "SaveEditor"
    )
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", str(app_executable))
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    synthetic_save = str(tmp_path / "synthetic.sav")
    program, arguments = self_command("--peek", synthetic_save)

    assert program == str(app_executable)
    assert arguments == ["--peek", synthetic_save]
