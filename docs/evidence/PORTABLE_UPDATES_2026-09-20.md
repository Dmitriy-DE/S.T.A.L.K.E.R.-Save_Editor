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

- `make test PYTHON=.venv/bin/python` — 532 passed;
- `make check PYTHON=.venv/bin/python` — ruff, mypy, docs-check and py_compile passed;
- hosted run `35481243962` — Linux and Windows packaging, source tests and
  packaged smoke passed; the release job reached Worker deploy but could not
  authenticate because repository Cloudflare secrets are absent;
- v0.5.14 GitHub Release assets and public R2 Worker matched by size and
  SHA-256: Windows ZIP `61982284` bytes,
  `cde107541d78070d982457669aaad25ae8f8d3edcf76cf297af8c204368da787`,
  Linux tar.gz `89778267` bytes,
  `78b78403faee2175a87c2e461f7cebd30a60fd1197550e4b0a0cf6b68848a946`,
  Debian package `93125592` bytes,
  `fe621d8fb5a4ec76f259e69f3f812c48e5bd84122299912d9790fc9b094e1e45`.
- `latest.json` public read-back matched the release asset;
  SHA-256 `3fa3221d6f25f8f8dd3626074e355d2113be6445deb064ac05eb3b598761aeeb`.
- Live update checks through the Worker returned `available 0.5.14` from
  `0.5.13` and `current` from `0.5.14` for both Linux and Windows targets.
- The privileged `.deb` install remains intentionally unrun; package contents,
  metadata, checksums and diagnostic runtime were verified.

## Boundaries

The updater is for the application installation only. It does not update save
files, Steam Cloud data, game assets, or Workshop content. Windows desktop
visual/DPI testing and game-specific Steam Cloud/game load tests remain
separate gates.
