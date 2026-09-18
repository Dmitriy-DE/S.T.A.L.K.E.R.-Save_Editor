"""Console entry point for one-shot native Steam Cloud child operations."""

from __future__ import annotations

import sys

from editor.steam_native import run_cli_op


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        index = arguments.index("--steam-native-op")
    except ValueError:
        print("Использование: SaveEditor-native --steam-native-op list|read|write", file=sys.stderr)
        return 2
    return run_cli_op(arguments[index + 1 :])


if __name__ == "__main__":
    raise SystemExit(main())
