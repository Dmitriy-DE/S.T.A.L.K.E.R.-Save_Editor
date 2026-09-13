#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null; then echo "Нужен Python 3" >&2; exit 1; fi
if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import tkinter
PY
then
  echo "Tkinter не установлен. Ubuntu/Debian:" >&2
  echo "  sudo apt update && sudo apt install -y python3-tk" >&2
  exit 2
fi
cd "$DIR"
exec "$PYTHON_BIN" app.py
