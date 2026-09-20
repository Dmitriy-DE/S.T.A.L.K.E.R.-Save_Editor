# Portable builds and in-app updates — evidence 2026-09-20

## Implemented

- Windows x86_64 portable ZIP remains a native PyInstaller target.
- Linux x86_64 portable tar.gz remains a native PyInstaller target.
- Linux amd64 .deb remains a separate package target.
- editor/update_manifest.py validates stable-channel metadata, target,
  architecture, URL host, size, and SHA-256.
- editor/updater.py downloads to a sibling temporary file, verifies before
  publishing, safely extracts ZIP/TAR, rejects traversal, and restores the old
  portable tree after a failed replacement or launch.
- ui/update_dialog.py and MainWindow run checks and downloads in Qt workers.
- tools/publish_release.py prepares stable R2 names, latest.json, and
  SHA256SUMS; the tag workflow uploads GitHub Release assets and R2 objects.

## Local evidence

At this snapshot:

- `make test PYTHON=.venv/bin/python` — 531 passed;
- `make check PYTHON=.venv/bin/python` — ruff, mypy, docs-check and py_compile passed;
- hosted run `35480101624` — Linux and Windows packaging, source tests and
  packaged smoke passed;
- v0.5.11 GitHub Release assets and public R2 Worker matched by size and
  SHA-256: Windows ZIP `61977876` bytes,
  `107ab9e09f11672d2df25a0feb23ceb1a78336588b0f5f0674bd2e1f2c2e9fb1`,
  Linux tar.gz `89763990` bytes,
  `668c4ed406588d59ff4289f69847043db5ed2b72ad619298bfadb4fe57f6142c`,
  Debian package `93116720` bytes,
  `f295e792bcad6367595d85418fcfd631e45fbccd1bb7b01f3cbbdcb343444d08`.
- `latest.json` public read-back matched the release asset;
  SHA-256 `e6a272d646a79c925f7f1172e6a32c73b287afda42b8393637e537bf52f3ac68`.
- Live update check through the Worker returned `available 0.5.11` from
  `0.5.10` and `current` from `0.5.11`.
- The privileged `.deb` install remains intentionally unrun; package contents,
  metadata, checksums and diagnostic runtime were verified.

## Boundaries

The updater is for the application installation only. It does not update save
files, Steam Cloud data, game assets, or Workshop content. Windows desktop
visual/DPI testing and game-specific Steam Cloud/game load tests remain
separate gates.
