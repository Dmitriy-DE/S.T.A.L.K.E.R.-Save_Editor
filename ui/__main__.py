from __future__ import annotations

import sys


def main() -> int:
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

    app = QApplication(sys.argv)
    window = MainWindow(EditorService())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
