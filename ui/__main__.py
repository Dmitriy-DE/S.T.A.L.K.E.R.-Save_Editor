from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import sys
from pathlib import Path


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
    if "--steam-native-op" in arguments:
        # Isolated one-shot native cloud op (spawned by the subprocess worker).
        # Runs without creating a Qt window, so a hung SteamAPI call stays in
        # this short-lived child that the parent can kill on timeout.
        from editor.steam_native import run_cli_op

        index = arguments.index("--steam-native-op")
        return run_cli_op(arguments[index + 1 :])
    if "--help" in arguments or "-h" in arguments:
        print("Использование: SaveEditor [--help]\nОткройте Qt окно редактора локальных сохранений.")
        return 0
    from editor.diagnostics import configure_logging

    configure_logging()
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        print(
            "Qt UI не установлен. Выполните: python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        print(f"Детали: {exc}", file=sys.stderr)
        return 2

    from editor.service import EditorService

    from .main_window import MainWindow

    app = QApplication([sys.argv[0], *arguments])
    app.setApplicationName("S.T.A.L.K.E.R. Save Editor")
    from PySide6.QtGui import QIcon

    icon_roots = [Path(__file__).resolve().parents[1]]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        icon_roots.insert(0, Path(bundle))
    for root in icon_roots:
        for name in ("app_icon.svg", "app_icon_256.png"):
            candidate = root / "assets" / name
            if candidate.is_file():
                app.setWindowIcon(QIcon(str(candidate)))
                break
        else:
            continue
        break
    window = MainWindow(EditorService())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
