"""Console entry point for one-shot native Steam Cloud child operations."""

from __future__ import annotations

import sys

from editor.steam_native import run_cli_op


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    # Read-only background jobs of the desktop UI (ui/worker_process.py).
    if "--peek" in arguments:
        from ui.save_peek import peek_main

        return peek_main(arguments[arguments.index("--peek") + 1 :])
    if "--extract-game-audio" in arguments:
        from ui.game_audio import extract_main

        return extract_main(arguments[arguments.index("--extract-game-audio") + 1 :])
    try:
        index = arguments.index("--steam-native-op")
    except ValueError:
        print("Использование: SaveEditor-native --steam-native-op list|read|write", file=sys.stderr)
        return 2
    return run_cli_op(arguments[index + 1 :])


if __name__ == "__main__":
    raise SystemExit(main())
