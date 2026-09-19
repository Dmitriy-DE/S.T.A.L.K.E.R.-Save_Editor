# Portable Builds, R2 Releases, and In-App Updates

**Status:** approved design, implementation pending

**Date:** 2026-09-20

## Goal

Publish reproducible Windows x86_64 and Linux x86_64 portable bundles alongside
the existing Linux Debian package, keep the exact artifacts available through
GitHub Releases and the existing Cloudflare R2 download worker, and let the
desktop application check for and safely install compatible updates without
blocking the Qt UI or corrupting the current installation.

## User-visible result

- The web download buttons continue to use the R2 worker and always point at
  the current stable artifacts.
- A stable release has one version and one release manifest. The manifest
  records the target, architecture, artifact name, size, SHA-256, and public
  download URL for each supported artifact.
- Windows users receive a portable ZIP containing the onedir application and
  its bundled runtime; no Python or installer is required.
- Linux users receive a portable tar.gz with the same property, plus the
  existing `.deb` for package-manager installation.
- The application performs a non-blocking update check at startup and exposes a
  manual check action. It reports no-update, unavailable, and update-ready
  states without treating a network failure as an application failure.
- A downloaded update is staged, hash-checked, and applied by a separate
  updater process after the GUI exits. Interrupted replacement preserves the
  previous installation and can be rolled back.

## Scope and boundaries

In scope:

- Windows x86_64 portable ZIP.
- Linux x86_64 portable tar.gz.
- Linux amd64 `.deb` publication and a package-manager handoff from the update
  dialog when the running application is a Debian installation.
- GitHub Release assets, R2 stable objects, `latest.json`, and read-back checks.
- One shared update protocol for all desktop targets.
- Unit, integration, packaging, and CI-contract tests.
- A focused code review of release, packaging, update, UI, and deployment code.

Out of scope:

- Committing large binary files into normal source-tree history. GitHub Release
  assets are the Git-hosted binary source of record.
- Silent privileged installation of a `.deb`; the user must approve the system
  package-manager action.
- Browser self-update. The browser remains a static editor/download surface.
- Automatic updates of game saves, Steam Cloud data, or user files.
- Cryptographic signing infrastructure. HTTPS plus manifest SHA-256 is the
  initial integrity contract; signing can be added as a separate release gate.
- Cross-compiling. Windows artifacts are built on Windows and Linux artifacts
  are built on Linux.

## Release contract

The release version is read from `VERSION`. A release job collects the exact
Linux and Windows build outputs, creates or updates the GitHub Release for the
tag, and publishes the same bytes to the R2 bucket behind the existing worker.

R2 stable keys remain predictable:

- `SaveEditor-windows-x86_64.zip`
- `SaveEditor-linux-x86_64.tar.gz`
- `stalker2-save-editor_amd64.deb`
- `latest.json`

The manifest is generated from the final files, never from filenames alone:

```json
{
  "schema": 1,
  "channel": "stable",
  "version": "0.5.9",
  "source_commit": "<full sha>",
  "published_at": "<UTC ISO-8601>",
  "artifacts": {
    "windows-x86_64": {
      "kind": "portable",
      "file": "SaveEditor-windows-x86_64.zip",
      "size": 0,
      "sha256": "<64 lowercase hex chars>",
      "url": "https://save-editor-downloads.save-editor.workers.dev/SaveEditor-windows-x86_64.zip"
    },
    "linux-x86_64": {
      "kind": "portable",
      "file": "SaveEditor-linux-x86_64.tar.gz",
      "size": 0,
      "sha256": "<64 lowercase hex chars>",
      "url": "https://save-editor-downloads.save-editor.workers.dev/SaveEditor-linux-x86_64.tar.gz"
    },
    "linux-deb-amd64": {
      "kind": "package",
      "file": "stalker2-save-editor_amd64.deb",
      "size": 0,
      "sha256": "<64 lowercase hex chars>",
      "url": "https://save-editor-downloads.save-editor.workers.dev/stalker2-save-editor_amd64.deb"
    }
  }
}
```

The manifest does not contain credentials, local paths, saves, or mutable
redirects. The worker serves it as JSON with a short cache lifetime; binary
objects retain attachment disposition and a cache policy suitable for stable
release files.

## Update architecture

`editor/updates.py` owns the platform-neutral protocol:

- read the current packaged version and installation kind;
- fetch and validate `latest.json` with a bounded timeout;
- compare versions using a strict, non-ambiguous version ordering;
- select only the current platform and architecture artifact;
- stream the artifact to a temporary file outside the installation directory;
- verify exact size and SHA-256 before any replacement;
- return typed states for current, available, unavailable, invalid manifest,
  incompatible target, cancelled, and failed download.

The updater must use dependency-free standard-library code so it is available
inside the frozen bundle. It must never execute a downloaded file before hash
verification, must not follow an untrusted artifact URL outside the configured
R2 host, and must leave the current installation untouched on every failed
path.

`packaging/updater_entry.py` is a small console entry point included in every
standalone bundle. The GUI starts it with an explicit staging directory,
installation directory, artifact kind, and expected hash. The updater waits
for the parent process to exit, extracts into a sibling staging directory,
validates the expected executable/manifest, renames the old installation to a
recoverable backup, installs the new directory, and removes the backup only
after the new executable has started successfully. A failed rename or launch
restores the old directory.

For `.deb`, the updater downloads and verifies the package, then invokes the
platform package-manager handoff with user confirmation. It does not run
`dpkg` silently or claim that a system package was upgraded before the child
process returns success.

## Qt integration

The main window keeps its existing synchronous construction path. After the
window is shown, a worker performs the update check and emits a result to the
UI thread. The check has no Steam, save, or parser dependency and is skipped
only when the user has disabled it or when the current installation is a
development checkout without an update channel.

The version badge gains a small update state and a manual action in the
existing support/settings surface. The dialog shows current version, target
version, target type, size, and verification status. Download/apply runs off
the UI thread; restart is explicit. Closing the dialog cancels only the
download and never damages the current installation.

## CI and publication

The existing matrix remains the source-test gate. The standalone workflow is
extended as follows:

1. Build Linux and Windows on their native hosted runners.
2. Run packaged diagnostics on both artifacts.
3. Upload per-target artifacts to the workflow run.
4. On a version tag, collect both outputs in one release job.
5. Generate `latest.json` from the exact files and source commit.
6. Publish/update GitHub Release assets and checksums.
7. Upload stable objects and `latest.json` to R2 with Wrangler.
8. Read every R2 object back through the public worker, compare byte count and
   SHA-256, and fail the release job on any mismatch.

R2 credentials are GitHub Actions secrets only. The source test workflow stays
read-only and never receives cloud credentials. Manual local publication uses
the same manifest generator and requires an explicit `--publish` action.

## Failure handling

- No network/DNS/TLS: show `Проверка обновлений недоступна`, keep the app usable.
- Invalid JSON/schema/version: reject the manifest and do not offer an update.
- Missing target artifact: report that the release is not available for this
  platform.
- Hash or size mismatch: delete the temporary download and keep the old app.
- Download cancellation: delete only the temporary download.
- Replacement failure: restore the backup and report the exact path.
- Update check hangs: enforce connect/read/overall timeouts and never block Qt.
- R2 publication mismatch: fail before the release is reported as published.

## Verification

- TDD tests for manifest validation, version comparison, target selection,
  bounded network errors, streaming hash verification, and staging paths.
- Updater integration tests using a local HTTP server and temporary install
  trees, including cancellation, corrupt bytes, interrupted replacement, and
  rollback.
- UI tests for no-update, update-available, unavailable, and manual-check
  states without a real network.
- Packaging tests proving both portable artifacts contain the updater,
  `BUILD_MANIFEST.json`, notices, and no private/save files.
- CI contract tests proving native target builds, artifact collection, release
  manifest generation, R2 publication, and read-back verification are present.
- Full `pytest`, `make check`, Linux package build, packaged diagnostic, and
  Windows runner build/smoke.
- Public verification of `latest.json`, all three R2 download URLs, HTTP
  status, sizes, and SHA-256 after publication.

## Review and simplification pass

After the feature is green, review only the affected release surface. Remove
duplicate version readers, URL constants, checksum formatting, and platform
branching where the manifest/updater contract makes them unnecessary. Keep
parser and save-format behavior unchanged unless a test demonstrates a
release/update regression. Record remaining external gates explicitly: actual
Windows desktop visual QA, privileged `.deb` installation, and user-owned
Steam/game load tests.
