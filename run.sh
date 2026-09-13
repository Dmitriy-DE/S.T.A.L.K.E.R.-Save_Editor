#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then echo "Нужен python3" >&2; exit 1; fi
if ! python3 - <<'PY' >/dev/null 2>&1
import tkinter
PY
then
  echo "Tkinter не установлен. Ubuntu/Debian:" >&2
  echo "  sudo apt update && sudo apt install -y python3-tk" >&2
  exit 2
fi
exec python3 app.py
