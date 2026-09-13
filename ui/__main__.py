from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
from pathlib import Path
import sys


def diagnostic_main(argv: list[str] | None = None) -> int:
    """Print a dependency/path report without opening a desktop window."""

    parser = argparse.ArgumentParser(
        prog="SaveEditor-diagnostic",
        description="Check bundled Qt and native decoder availability",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="probe the bundled decoder and print JSON",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not args.diagnostic:
        parser.print_help()
        return 0

    from editor.codec import CodecError, load_decoder
    from editor.platforms import discover_helper

    helper = discover_helper()
    try:
        qt_version = importlib.metadata.version("PySide6")
    except importlib.metadata.PackageNotFoundError:
        qt_version = "bundled"
    report: dict[str, object] = {
        "platform": sys.platform,
        "machine": platform.machine(),
        "executable": sys.executable,
        "qt": qt_version if importlib.util.find_spec("PySide6") is not None else "missing",
        "helper": str(helper) if helper else None,
        "bundle_root": str(Path(__file__).resolve().parent.parent),
    }
    try:
        decoder = load_decoder()
    except CodecError as exc:
        report.update({"decoder": "error", "decoder_error": str(exc)})
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    report.update(
        {
            "decoder": "loaded",
            "decoder_path": str(getattr(decoder, "__file__", "<embedded>")),
        }
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if "--diagnostic" in arguments:
        return diagnostic_main(arguments)
    if "--help" in arguments or "-h" in arguments:
        print("Использование: SaveEditor [--help]\nОткройте Qt окно редактора локальных .sav.")
        return 0
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        print(
            "Qt UI не установлен. Выполните: python -m pip install -r requirements-ui.txt",
            file=sys.stderr,
        )
        print(f"Детали: {exc}", file=sys.stderr)
        return 2

    from editor.service import EditorService
    from .main_window import MainWindow

    app = QApplication([sys.argv[0], *arguments])
    window = MainWindow(EditorService())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
