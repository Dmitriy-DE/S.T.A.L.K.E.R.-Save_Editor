#!/usr/bin/env python3
"""Small line-delimited JSON helper used only by worker lifecycle tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


MODE = os.environ.get("FAKE_WORKER_MODE", "normal")
MARKER = Path(os.environ["FAKE_WORKER_MARKER"]) if os.environ.get("FAKE_WORKER_MARKER") else None
DELAY = float(os.environ.get("FAKE_WORKER_DELAY", "0.3"))


def emit(payload: dict[str, object], *, chunked: bool = False) -> None:
    text = json.dumps(payload, separators=(",", ":")) + "\n"
    if chunked:
        for char in text:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(0.001)
    else:
        sys.stdout.write(text)
        sys.stdout.flush()


def main() -> int:
    if MODE == "stderr_flood":
        sys.stderr.write("stderr-flood " * 200_000)
        sys.stderr.flush()
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except Exception:
            emit({"type": "Error", "message": "bad request"})
            continue
        kind = request.get("type")
        if MODE == "crash":
            return 3
        if MODE == "oversize":
            sys.stdout.write("x" * 4096 + "\n")
            sys.stdout.flush()
            continue
        if MODE == "malformed":
            sys.stdout.write("this is not json\n")
            sys.stdout.flush()
            continue
        if kind == "Ping":
            emit({"type": "Pong"}, chunked=MODE == "chunked")
        elif kind == "Connect":
            emit({"type": "Connected"})
        elif kind == "GetFiles":
            if MODE == "delayed_once" and MARKER is not None and not MARKER.exists():
                MARKER.write_text("delayed", encoding="utf-8")
                time.sleep(DELAY)
            emit({"type": "Files", "files": []})
        elif kind == "ReadFile":
            emit({"type": "FileData", "data": [1, 2, 3]})
        elif kind == "WriteFile":
            emit({"type": "Ok"})
        elif kind == "SyncCloudFiles":
            emit({"type": "Ok"})
        elif kind == "Exit":
            emit({"type": "Ok"})
            return 0
        else:
            emit({"type": "Error", "message": f"unknown request {kind}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
