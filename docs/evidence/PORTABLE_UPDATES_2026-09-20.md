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

- `make test PYTHON=.venv/bin/python` — 530 passed;
- `make check PYTHON=.venv/bin/python` — ruff, mypy, docs-check and py_compile passed;
- hosted run `35479286615` — Linux and Windows packaging, source tests and
  packaged smoke passed;
- v0.5.10 GitHub Release assets and public R2 Worker matched by size and
  SHA-256: Windows ZIP `61977876` bytes,
  `d598b93606fd16d2e4fe7e87b0a28a372d9cbf45fd0d80715775751795a9d58b`,
  Linux tar.gz `89760944` bytes,
  `b6c44136d8641711c0551fc957d0e2a3c1587060e67421e83d6aaf48b3809166`,
  Debian package `93116640` bytes,
  `82742efdacb510cdbb978dda2ea6d7e4d7cf0c032f550bb1bde6cd6860ff7b9e`.
- `latest.json` public read-back matched the release asset;
  SHA-256 `d60e2d4c244fff1ace6c756aa6b14e8d2f134a8a314498f61e0c1231dee0407e`.
- The privileged `.deb` install remains intentionally unrun; package contents,
  metadata, checksums and diagnostic runtime were verified.

## Boundaries

The updater is for the application installation only. It does not update save
files, Steam Cloud data, game assets, or Workshop content. Windows desktop
visual/DPI testing and game-specific Steam Cloud/game load tests remain
separate gates.
