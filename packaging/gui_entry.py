"""PyInstaller entry point that preserves the ``ui`` package context."""

from ui.__main__ import main

raise SystemExit(main())
