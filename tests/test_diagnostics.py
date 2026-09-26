from __future__ import annotations

import gzip
import json
import logging
import os
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


def test_cleanup_logs_enforces_age_and_total_budget_without_touching_other_files(
    tmp_path: Path,
) -> None:
    now = 1_800_000_000.0
    current = tmp_path / "save-editor.log"
    recent_backup = tmp_path / "save-editor.log.1"
    old_backup = tmp_path / "save-editor.log.2"
    unrelated_backup = tmp_path / "save-backup.sav"
    current.write_bytes(b"c" * 60)
    recent_backup.write_bytes(b"r" * 50)
    old_backup.write_bytes(b"o" * 40)
    unrelated_backup.write_bytes(b"keep")
    os.utime(current, (now, now))
    os.utime(recent_backup, (now - 10, now - 10))
    os.utime(old_backup, (now - 120, now - 120))

    removed = diagnostics.cleanup_logs(
        tmp_path,
        max_age_seconds=60,
        max_total_bytes=100,
        now=now,
    )

    assert old_backup in removed
    assert not old_backup.exists()
    assert unrelated_backup.exists()
    assert sum(path.stat().st_size for path in tmp_path.glob("save-editor.log*")) <= 100


def test_collect_log_bundle_redacts_steam_ids_and_file_contents_but_keeps_safe_metadata(
    tmp_path: Path,
) -> None:
    (tmp_path / "save-editor.log").write_text(
        "operation=cloud backend=web release=v0.5.20 size=42 sha256=abc123 "
        "exception=TimeoutError steam_id=76561198012345678 "
        "save_bytes=deadbeef contents=PRIVATE SAVE CONTENT operation=cloud\n",
        encoding="utf-8",
    )

    text = gzip.decompress(diagnostics.collect_log_bundle(tmp_path)).decode("utf-8")

    assert "operation=cloud" in text
    assert "backend=web" in text
    assert "release=v0.5.20" in text
    assert "size=42" in text
    assert "sha256=abc123" in text
    assert "exception=TimeoutError" in text
    assert "76561198012345678" not in text
    assert "deadbeef" not in text
    assert "PRIVATE_SAVE_CONTENT" not in text
    assert "PRIVATE SAVE CONTENT" not in text


def test_collect_log_bundle_is_empty_when_log_directory_does_not_exist(
    tmp_path: Path,
) -> None:
    payload = diagnostics.collect_log_bundle(tmp_path / "missing")

    assert gzip.decompress(payload) == b""


def test_collect_log_bundle_reads_only_the_bounded_log_tail(tmp_path: Path) -> None:
    (tmp_path / "save-editor.log").write_text(
        "old-secret-line\n" + "x" * 10000 + "latest-safe-line\n",
        encoding="utf-8",
    )

    text = gzip.decompress(
        diagnostics.collect_log_bundle(tmp_path, max_bytes=128)
    ).decode("utf-8")

    assert "latest-safe-line" in text
    assert "old-secret-line" not in text


def test_collect_log_bundle_normalizes_platform_newlines(tmp_path: Path) -> None:
    (tmp_path / "save-editor.log").write_bytes(b"first\r\nsecond\r\n")

    text = gzip.decompress(diagnostics.collect_log_bundle(tmp_path)).decode("utf-8")

    assert "first\nsecond\n" in text
    assert "\r" not in text


def test_export_log_bundle_writes_redacted_payload_without_deleting_logs(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "save-editor.log"
    export_path = tmp_path / "manual" / "diagnostics.log.gz"
    log_path.write_text("token=SECRET operation=cloud\n", encoding="utf-8")

    result = diagnostics.export_log_bundle(export_path, directory=tmp_path)

    assert result == export_path
    assert gzip.decompress(export_path.read_bytes()).find(b"SECRET") == -1
    assert log_path.is_file()


def test_submit_logs_rejects_oversized_payload_before_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called = False

    def fake_urlopen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not receive an oversized bundle")

    monkeypatch.setattr(diagnostics, "collect_log_bundle", lambda *_args, **_kwargs: b"x" * (diagnostics.MAX_UPLOAD_BYTES + 1))
    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(diagnostics.DiagnosticsError, match="слишком большие"):
        diagnostics.submit_logs(
            endpoint="https://save-editor-downloads.save-editor.workers.dev/diagnostics",
            directory=tmp_path,
        )

    assert called is False


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


@pytest.mark.parametrize(
    ("line", "secrets"),
    (
        ("Authorization: Bearer REAL_BEARER_TOKEN", ("REAL_BEARER_TOKEN",)),
        ("authorization=Bearer REAL_EQUALS_TOKEN", ("REAL_EQUALS_TOKEN",)),
        (
            "Cookie: session=REAL_COOKIE_SECRET; auth=REAL_COOKIE_AUTH",
            ("REAL_COOKIE_SECRET", "REAL_COOKIE_AUTH"),
        ),
        ("token=REAL_TOKEN_SECRET", ("REAL_TOKEN_SECRET",)),
        ("password: REAL_PASSWORD_SECRET", ("REAL_PASSWORD_SECRET",)),
        (
            "https://example.invalid/callback?token=URL_TOKEN&access_token=URL_ACCESS&api_key=URL_API",
            ("URL_TOKEN", "URL_ACCESS", "URL_API"),
        ),
    ),
)
def test_collect_log_bundle_redacts_complete_credentials(
    tmp_path: Path,
    line: str,
    secrets: tuple[str, ...],
) -> None:
    (tmp_path / "save-editor.log").write_text(line, encoding="utf-8")

    text = gzip.decompress(diagnostics.collect_log_bundle(tmp_path)).decode("utf-8")

    for secret in secrets:
        assert secret not in text
    assert "<redacted>" in text
    assert "Bearer REAL_" not in text


def test_collect_log_bundle_redacts_quoted_json_credentials(tmp_path: Path) -> None:
    (tmp_path / "save-editor.log").write_text(
        '{"token":"JSON_TOKEN", "authorization": "Bearer JSON_AUTH"}',
        encoding="utf-8",
    )

    text = gzip.decompress(diagnostics.collect_log_bundle(tmp_path)).decode("utf-8")

    assert "JSON_TOKEN" not in text
    assert "JSON_AUTH" not in text
    assert '"token":"<redacted>"' in text


@pytest.mark.parametrize(
    ("line", "private_path"),
    (
        (r"path=C:\Users\Dmytro\AppData\Local\Steam\slot.sav", r"C:\Users\Dmytro"),
        ("path=/home/dmytro/.steam/steam/slot.sav", "/home/dmytro"),
    ),
)
def test_collect_log_bundle_redacts_platform_home_paths(
    tmp_path: Path,
    line: str,
    private_path: str,
) -> None:
    (tmp_path / "save-editor.log").write_text(line, encoding="utf-8")

    text = gzip.decompress(diagnostics.collect_log_bundle(tmp_path)).decode("utf-8")

    assert private_path not in text
    assert "<home>" in text


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
        environment_report="Environment: OK",
    )

    assert report_id == "20260921-abc"
    assert seen["timeout"] == diagnostics.DEFAULT_TIMEOUT
    assert seen["request"].get_header("Content-type") == "application/gzip"
    assert b"cloud operation failed\n" in gzip.decompress(seen["request"].data)
    assert b"Environment: OK" in gzip.decompress(seen["request"].data)
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
