# Steam Cloud Diagnostics and OTA Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Steam Cloud reads use the backend that discovered each file, make failures diagnosable without filling the disk, and make verified package/portable updates behave truthfully on Linux and Windows.

**Architecture:** Add explicit provenance to `CloudFile` and keep the selected entry through the cloud read path. Cache metadata remains read-only; a local cache copy is read locally, web metadata is upgraded through CDP when available, and native `FileRead` is never attempted for a cache-only entry. Add one small stdlib diagnostics module with rotating local logs and a redacted gzip upload to the existing R2 Worker. Keep OTA handoff explicit: verified `.deb`/installer files go to the OS installer, while portable archives go to the existing external updater.

**Tech Stack:** Python 3.11+, PySide6, pytest, stdlib `logging`/`urllib`/`gzip`, Cloudflare Worker + R2, existing release manifest and package workflow.

**Spec:** `docs/superpowers/specs/2026-09-20-portable-updater-r2-release-design.md`, plus the confirmed cache-provenance incident report supplied in the task.

## Global Constraints

- Unknown save structures and unverified Steam Cloud writes remain read-only or fail closed.
- Cloud upload behavior is unchanged until a live write is positively verified; this pass fixes discovery/read routing and diagnostics.
- Logs never contain save bytes and local paths are redacted before upload.
- Log files rotate at a bounded size with a bounded backup count; the Worker accepts only bounded gzip payloads and exposes no read endpoint.
- Updates verify manifest host, artifact size and SHA-256 before any installer handoff or portable replacement.
- No personal saves, Steam session material, credentials, or generated private fixtures enter Git.

## Review Focus

- Cache metadata names with no local `remote/` file must not invoke native `FileExists`/`FileRead`; test the exact S2 path from the incident.
- A cache file whose local byte size disagrees with metadata must not be silently used; test explicit refusal and the web upgrade path.
- A failed diagnostics upload must preserve local logs and a successful upload must return a non-secret report id; test both paths.
- A `.deb` update must launch the package handoff only after verified download and must report that installation still needs user confirmation; test without running `dpkg`.
- The current v0.5.14 client must be diagnosed as an old build limitation; current source must not claim silent package self-replacement.

### Task 1: Cloud file provenance and read routing

**Files:**
- Modify: `steam_cloud.py` (`CloudFile`, source labels)
- Modify: `editor/steam_native.py` (native/helper/cache/CDP routing and cache validation)
- Modify: `editor/steam_cdp.py` (source labels and cache metadata/local source)
- Modify: `ui/cloud_view.py` (preserve the cloud entry during analyze and show source)
- Test: `tests/test_steam_cdp.py`, `tests/test_steam_native_subprocess.py`, `tests/test_ui_cloud.py`

**Interfaces:**
- `CloudFile.source: str` is an additive field with a default for compatibility. Values are `native_remote_storage`, `helper_remote_storage`, `web`, `steam_cache_local`, `steam_cache_metadata`, or `unknown`.
- Cloud transports expose an entry-aware read path that accepts a `CloudFile`; legacy one-argument test doubles remain supported.

- [ ] Add failing tests for the six source values, exact-path cache metadata, local-cache size validation, and the rule that metadata-only reads never call native `read`.
- [ ] Run the focused tests and confirm they fail for the current implementation.
- [ ] Add provenance at every constructor and route entry-aware reads through local cache, CDP/web, helper, or native according to the entry source.
- [ ] Make cache-only failure explicit (`metadata found, content unavailable`) and retain write capability as read-only.
- [ ] Render a source/backend label instead of interpreting `Persisted: нет` as “not in Steam Cloud”.
- [ ] Run the focused cloud/UI tests and then the full Python suite.
- [ ] Commit as `fix: route Steam Cloud reads by provenance`.

### Task 2: Bounded local logs and one-click diagnostics upload

**Files:**
- Create: `editor/diagnostics.py`
- Create: `ui/diagnostics_dialog.py`
- Modify: application startup module and `ui/main_window.py` to configure logging and expose `Отправить логи`
- Modify: cloud/update workers to log operation start, backend, result and exception class without save bytes
- Modify: `infra/downloads-worker/worker.js` and `infra/downloads-worker/wrangler.toml` for `POST /diagnostics`
- Test: `tests/test_diagnostics.py`, `tests/test_downloads_worker.py`, relevant UI tests

**Interfaces:**
- `editor.diagnostics.configure_logging()` is idempotent and returns the active log path.
- `editor.diagnostics.collect_log_bundle()` returns a bounded redacted gzip payload.
- `editor.diagnostics.submit_logs(endpoint=...)` returns a report id or raises a user-safe diagnostics error.
- Worker `POST /diagnostics` returns `{ "report_id": "..." }`, accepts bounded `application/gzip`, stores under `diagnostics/`, and never serves stored objects.

- [ ] Write failing tests for rotation bounds, redaction of home/user paths, no save bytes in the bundle, upload response/error handling, body-size/content-type rejection, and absent GET access.
- [ ] Run those tests to confirm red.
- [ ] Implement the rotating handler and bounded collection using the existing platform data directory; log to at most 1 MiB plus three backups.
- [ ] Add the Qt dialog/button with a background worker, clear success report id, and clear failure state; keep the operation optional and non-blocking.
- [ ] Implement the Worker endpoint with a random object id, no-cache response, bounded body, and R2 `diagnostics/` prefix. Configure lifecycle expiry for old diagnostic objects using the supported Wrangler/R2 mechanism.
- [ ] Run diagnostics, Worker contract, UI, and full source checks.
- [ ] Commit as `feat: add bounded diagnostics reporting`.

### Task 3: OTA handoff and release-facing diagnostics

**Files:**
- Modify: `editor/updater.py` and `ui/update_dialog.py`
- Modify: `tests/test_updater.py` and update UI tests
- Modify: `README.md`, `docs/STATUS.md`, `docs/RELEASE.md`, and a new evidence note for the incident

**Interfaces:**
- Add a tested package/installer handoff helper that launches only a previously hash-verified artifact and reports “opened, installation pending”.
- Portable replacement continues through the existing updater executable and remains atomic/recoverable.

- [ ] Add failing tests for Linux package handoff, Windows installer handoff, portable routing, and the exact user-facing state after an installer is opened.
- [ ] Run the tests to confirm red.
- [ ] Implement the smallest handoff change; do not run privileged installation from the application and do not claim an update completed before the OS/package manager confirms it.
- [ ] Log manifest version, artifact kind, verification result and handoff result without user paths or file contents.
- [ ] Document why v0.5.14 could not apply the current OTA path and the one-time upgrade path to v0.5.17/current release.
- [ ] Run updater tests, package diagnostics, and `make check`.
- [ ] Commit as `fix: make OTA handoff observable and safe`.

### Task 4: Final review, build, publication and cleanup

**Files:**
- Modify: `VERSION`, release notes/evidence, generated web metadata only if checks require it
- Verify: GitHub workflow, R2 manifest/artifacts, Pages download links, local branches/worktrees/caches

- [ ] Run the full source gate, dead-code/unused-symbol scan, generated-file checks, Linux package build and packaged diagnostics.
- [ ] Review the complete diff for accidental save paths, secrets, duplicate UI paths, and unsupported claims.
- [ ] Bump the release version only after the branch is green; generate exact artifacts and SHA-256 manifest.
- [ ] Publish the Worker/R2 and GitHub release assets through the existing release path, then read back `latest.json` and every advertised artifact.
- [ ] Verify Pages points to separate Windows installer/portable and Linux portable/package downloads.
- [ ] Record local versus hosted versus live Steam/game evidence explicitly.
- [ ] Remove only task-created worktrees/caches/temp files and stale local branches; leave the project, docs, builds and release evidence.
- [ ] Request a fresh-context code review, fix all actionable findings, rerun the final gate, and report exact SHA/release/R2 status.

