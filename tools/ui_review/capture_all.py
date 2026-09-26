#!/usr/bin/env python3
"""Screenshot every main page and dialog in every interface language.

    python tools/ui_review/capture_all.py OUT_DIR [--langs ru,en,...]

Uses only synthetic test fixtures and a throw-away HOME, so the images carry
no personal saves or paths and can be shared for review.  Besides the PNGs it
writes ``clipped.json``: widgets whose text needs more room than they got —
the machine-found candidates for truncated UI (docs/roadmap ST-5).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIZES = ((1180, 620), (1366, 768), (1920, 1080))


def _languages() -> list[str]:
    return ["ru", *sorted(p.stem for p in (ROOT / "locales").glob("*.json") if not p.stem.startswith("_"))]


def _clipped(widget) -> list[dict]:
    from PySide6.QtWidgets import QAbstractButton, QLabel

    found = []
    for child in [*widget.findChildren(QLabel), *widget.findChildren(QAbstractButton)]:
        if not child.isVisible() or not child.text().strip():
            continue
        if isinstance(child, QLabel) and child.wordWrap():
            need = child.heightForWidth(child.width())
            if need > child.height() + 4:
                found.append({"widget": child.objectName() or type(child).__name__, "text": child.text()[:80], "need_h": need, "has_h": child.height()})
            continue
        # A few pixels are layout rounding; real truncation is visibly more.
        need = max(child.sizeHint().width(), child.fontMetrics().horizontalAdvance(child.text()))
        if need > child.width() + 12:
            found.append({"widget": child.objectName() or type(child).__name__, "text": child.text()[:80], "need_w": need, "has_w": child.width()})
    return found


def _child(language: str, out: Path) -> int:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tests"))
    from PySide6.QtWidgets import QApplication

    app = QApplication([])
    from test_xray_save import _fixture

    from editor.service import EditorService
    from ui.diagnostics_dialog import DiagnosticsDialog
    from ui.main_window import LocalSnapshot, MainWindow
    from ui.support_dialog import SupportDialog

    def settle() -> None:
        # Let page fade-ins finish so the screenshot shows the final layout.
        from PySide6.QtCore import QDeadlineTimer, QThread

        deadline = QDeadlineTimer(900)
        while not deadline.hasExpired():
            app.processEvents()
            QThread.msleep(15)

    report: dict[str, list[dict]] = {}

    def shot(widget, name: str) -> None:
        settle()
        widget.grab().save(str(out / f"{language}_{name}.png"))
        clipped = _clipped(widget)
        if clipped:
            report[name] = clipped

    service = EditorService()
    window = MainWindow(service, auto_update_check=False)
    window.show()
    save = out / "synthetic_cop.sav"
    data = _fixture()
    save.write_bytes(data)
    result = service.inspect_result(data, source_name=str(save))
    snapshot = LocalSnapshot(
        path=save, data=data, info=result.info, format_id=result.format_id, format_title=result.format_title,
        release_id=result.release_id, edition=result.edition, capabilities=result.capabilities,
        catalog=result.catalog, game_catalog=result.game_catalog, display_catalog=result.display_catalog,
    )
    for width, height in SIZES:
        window.resize(width, height)
        size = f"{width}x{height}"
        window._on_reference_destination("library")
        shot(window, f"library_{size}")
        window._on_reference_destination("settings")
        shot(window, f"settings_{size}")
        window._on_reference_destination("history")
        shot(window, f"history_{size}")
        window._render_snapshot(snapshot)
        shot(window, f"editor_{size}")
        window._show_character_state()
        shot(window, f"character_{size}")
    for name, factory in (("diagnostics", lambda: DiagnosticsDialog(window)), ("support", lambda: SupportDialog(window))):
        dialog = factory()
        dialog.show()
        shot(dialog, f"dialog_{name}")
        dialog.close()
    (out / f"{language}_clipped.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    save.unlink()
    os._exit(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--langs")
    parser.add_argument("--child", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.child:
        return _child(args.child, args.out)
    languages = args.langs.split(",") if args.langs else _languages()
    summary = {}
    for language in languages:
        with tempfile.TemporaryDirectory() as home:
            env = {**os.environ, "HOME": home, "XDG_DATA_HOME": f"{home}/.local/share", "XDG_CONFIG_HOME": f"{home}/.config",
                   "STALKER_EDITOR_LANG": language, "QT_QPA_PLATFORM": "offscreen"}
            subprocess.run([sys.executable, __file__, str(args.out), "--child", language], env=env, check=False, timeout=300)
        path = args.out / f"{language}_clipped.json"
        summary[language] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"error": ["child failed"]}
        count = sum(len(v) for v in summary[language].values())
        print(f"{language}: {count} clipped candidates")
    (args.out / "clipped.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
