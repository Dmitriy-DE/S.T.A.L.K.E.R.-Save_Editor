from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from urllib.error import URLError

import pytest

from editor import diagnostics


def test_configure_logging_rotates_with_bounded_backups(tmp_path: Path) -> None:
    logger = diagnostics.configure_logging(
        tmp_path,
        max_bytes=256,
        backup_count=2,
    )
    for _ in range(10):
        logging.getLogger("stalker2_save_editor.test").info("x" * 40)
    for handler in logging.getLogger("stalker2_save_editor").handlers:
        handler.flush()

    files = sorted(tmp_path.glob("save-editor.log*"))
    assert len(files) <= 3
    assert logger == tmp_path / "save-editor.log"
    assert all(path.stat().st_size <= 256 for path in files)


def test_collect_log_bundle_redacts_home_secrets_and_ignores_save_files(tmp_path: Path) -> None:
    (tmp_path / "save-editor.log").write_text(
        "path=/home/dmytro/.steam/steam token=SECRET\n"
        "cloud=Stalker2/Saved/STEAM/SaveGames/Data/slot.sav\n",
        encoding="utf-8",
    )
    (tmp_path / "private.sav").write_bytes(b"PRIVATE_SAVE_BYTES")

    payload = diagnostics.collect_log_bundle(tmp_path)
    text = gzip.decompress(payload).decode("utf-8")

    assert "/home/dmytro" not in text
    assert "SECRET" not in text
    assert "PRIVATE_SAVE_BYTES" not in text
    assert "slot.sav" in text


def test_submit_logs_returns_report_id_without_deleting_local_logs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "save-editor.log"
    log_path.write_text("cloud operation failed\n", encoding="utf-8")
    seen = {}

    class Response:
        status = 201

        def read(self, _limit: int | None = None) -> bytes:
            return json.dumps({"report_id": "20260921-abc"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def fake_urlopen(request, *, timeout):
        seen["request"] = request
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", fake_urlopen)
    report_id = diagnostics.submit_logs(
        endpoint="https://save-editor-downloads.save-editor.workers.dev/diagnostics",
        log_dir=tmp_path,
    )

    assert report_id == "20260921-abc"
    assert seen["timeout"] == diagnostics.DEFAULT_TIMEOUT
    assert seen["request"].get_header("Content-type") == "application/gzip"
    assert b"cloud operation failed\n" in gzip.decompress(seen["request"].data)
    assert log_path.is_file()


def test_submit_logs_preserves_logs_when_endpoint_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "save-editor.log"
    log_path.write_text("keep me\n", encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise URLError("offline")

    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", fail)
    with pytest.raises(diagnostics.DiagnosticsError, match="offline"):
        diagnostics.submit_logs(
            endpoint="https://save-editor-downloads.save-editor.workers.dev/diagnostics",
            log_dir=tmp_path,
        )
    assert log_path.read_text(encoding="utf-8") == "keep me\n"
