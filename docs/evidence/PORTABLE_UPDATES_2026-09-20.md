# Portable builds and in-app updates — evidence 2026-09-20

## Implemented

- Windows x86_64 portable ZIP remains a native PyInstaller target.
- Windows x86_64 installer EXE is built by Inno Setup from the same verified
  PyInstaller runtime tree and installs a normal Start Menu/desktop entry.
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
  The installer is an optional manifest artifact so older portable builds can
  still parse the required three-artifact contract and update to the ZIP.

## Local evidence

At this snapshot (`v0.5.15`, commit
`7306dcbde417e9374038d9d9f47d198e4dfc2053`):

- `make test PYTHON=.venv/bin/python` — 537 passed;
- `make check PYTHON=.venv/bin/python` — ruff, mypy, docs-check and py_compile passed;
- hosted run `35508107671` — Linux and Windows packaging, source tests,
  packaged diagnostics, Inno Setup compilation and installed Windows smoke
  passed; the release job reached Worker deploy but could not authenticate
  because repository Cloudflare secrets are absent;
- v0.5.15 GitHub Release assets and public R2 Worker matched by size and
  SHA-256: Windows ZIP `61985583` bytes,
  `39b6479e2e8a85610d00af5695f4448b5008994a566102cf62aee81ff3f4bf9b`,
  Windows installer `38187197` bytes,
  `54761d30ddb502c7b8c8a5dacb160a621030632a6a0e4dcac5bcfdb098b768dc`,
  Linux tar.gz `89762581` bytes,
  `3bb8e1290d5642d935c6232df823937d2b7863495a0f3472c4a7b7c166bb89b7`,
  Debian package `93138182` bytes,
  `9fdc4a5a70d83c88d3f5f2a61f358662d5276f81bcab531ec9621fd3ce056ada`;
- `latest.json` public read-back matched the release asset;
  SHA-256 `4bae8680c398acad8fb1bbbc65263ef4a716f8697762ae8a594d5af975511dd7`.
- Live update checks through the Worker returned `available 0.5.15` from
  `0.5.14` and `current` from `0.5.15` for Linux portable/package and Windows
  portable/installer selections; each selected the expected artifact.
- The privileged `.deb` install remains intentionally unrun; package contents,
  metadata, checksums and diagnostic runtime were verified.

## Boundaries

The updater is for the application installation only. It does not update save
files, Steam Cloud data, game assets, or Workshop content. Windows desktop
visual/DPI testing, privileged `.deb` installation and game-specific Steam
Cloud/game load tests remain separate gates.
