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

- pytest tests -q — 528 passed;
- targeted ruff/mypy checks for release/update files — passed;
- no hosted Windows build, R2 upload, public read-back, or privileged .deb
  installation has been run in this local checkout yet.

## Boundaries

The updater is for the application installation only. It does not update save
files, Steam Cloud data, game assets, or Workshop content. Windows desktop
visual/DPI testing and game-specific Steam Cloud/game load tests remain
separate gates.
