# Project Hardening and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the audited CI, Cloud, updater, web, release, and repository-quality defects and prepare one verified release.

**Architecture:** Introduce one explicit Cloud write-capability boundary, one redirect-safe updater boundary, and one testable browser bootstrap module.  Make the release workflow fail atomically, then remove only statically proven dead code and publish all channels from the same bytes.

**Tech Stack:** Python 3.11/3.12, PySide6, pytest, mypy, ruff, JavaScript ES modules/Node, GitHub Actions, Cloudflare Worker/R2/Pages.

**Spec:** `docs/superpowers/specs/2026-09-20-project-hardening-release-design.md`

## Global Constraints

- Do not write to a real Steam Cloud slot from automated tests.
- Do not enable unsupported save mutations or infer game acceptance from parser round-trips.
- Preserve backup, fresh-SHA, persisted, read-back, CRC, and decompression guards.
- Windows installer and portable ZIP remain separate artifacts; Linux portable tarball and Debian package remain separate artifacts.
- GitHub Release, R2, updater manifest, and Pages must describe one version.
- Use the existing pinned runtime and development dependencies; add no product dependency.

## Review Focus

- Native listing fails and CDP succeeds: listing/download work, upload is disabled, and no native write is attempted.
- A writer becomes unavailable between preflight and write: transaction reports a definite pre-write failure, not `uncertain`.
- Redirect target changes from an allowed hostname to a disallowed hostname resolving to the same machine: target receives no request.
- Backup cleanup fails after a successful portable launch: new installation remains active and callable.
- Catalog loading is slower than core startup: picker enables, but analysis waits and reports catalog failure clearly.

---

### Task 1: Cross-platform source and packaging gates

**Files:**
- Modify: `editor/updater.py`
- Modify: `.github/workflows/build.yml`
- Modify: `tests/test_ci_contract.py`

**Interfaces:**
- Consumes: existing `mypy.ini`, generated-file check scripts, and package workflow.
- Produces: updater ctypes lookup that type-checks on Linux and Windows; package jobs that run the complete source gate.

- [ ] **Step 1: Capture the Windows mypy failure**

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m mypy --platform win32`

Expected: FAIL at `editor/updater.py` because the two `type: ignore[attr-defined]` comments are unused on Windows.

- [ ] **Step 2: Add a failing package-gate contract test**

Add to `tests/test_ci_contract.py` a test that parses `.github/workflows/build.yml`, locates the package job, and requires commands for ruff, mypy, the three generated-file `--check` scripts, and pytest before the build step.

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_ci_contract.py -q`

Expected: FAIL because the package job currently runs pytest only.

- [ ] **Step 3: Implement the platform-neutral ctypes lookup and package gate**

Replace direct platform-dependent attributes with:

```python
win_dll = getattr(ctypes, "WinDLL")
get_last_error = getattr(ctypes, "get_last_error")
```

Add a package workflow source-gate step that invokes ruff, mypy, the generated-file check scripts, py_compile, and pytest using `sys.executable`.

- [ ] **Step 4: Verify both mypy platforms and CI contracts**

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m mypy && /home/dmytro/Projects/save-editor/.venv/bin/python -m mypy --platform win32 && /home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_ci_contract.py tests/test_updater.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add editor/updater.py .github/workflows/build.yml tests/test_ci_contract.py
git commit -m "fix: enforce cross-platform release gates"
```

### Task 2: Explicit Steam Cloud write capability

**Files:**
- Create: `editor/cloud_capabilities.py`
- Modify: `editor/transactions.py`
- Modify: `steam_cloud.py`
- Modify: `editor/steam_cdp.py`
- Modify: `editor/steam_native.py`
- Modify: `ui/cloud_view.py`
- Modify: `tests/test_cloud_transaction.py`
- Modify: `tests/test_steam_backend.py`
- Modify: `tests/test_steam_cdp.py`
- Modify: `tests/test_steam_native_subprocess.py`
- Modify: `tests/test_ui_cloud.py`

**Interfaces:**
- Consumes: every Cloud transport selected by `CloudOperationWorker`.
- Produces: `CloudWriteCapability`, `CloudWriteNotAttemptedError`, and `cloud_write_capability(transport) -> CloudWriteCapability` used by transactions and UI.

- [ ] **Step 1: Add failing capability and transaction tests**

Add tests proving an unadvertised/read-only transport is rejected before `read_file`, backup creation, or `write_file`; a typed post-preflight refusal raises `CloudTransactionError`; and an ambiguous ordinary write exception remains `uncertain`.

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_cloud_transaction.py -q`

Expected: FAIL because no capability contract exists and every write exception becomes `uncertain`.

- [ ] **Step 2: Add failing production-transport tests**

Add tests proving helper/native transports advertise writable, CDP/cache fallback advertises read-only, and `SteamNativeSubprocessWorker.write_file` does not call `_run_native` while a read-only fallback is selected.

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_steam_backend.py tests/test_steam_cdp.py tests/test_steam_native_subprocess.py -q`

Expected: FAIL because the transports do not expose capabilities and fallback write still calls native.

- [ ] **Step 3: Add failing UI tests**

Add a Qt test that supplies a prepared cloud edit with a read-only transport and asserts upload stays disabled while the reason is visible; switch capability to writable and assert upload enables.

Run: `QT_QPA_PLATFORM=offscreen /home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_ui_cloud.py -q`

Expected: FAIL because button state currently checks only `transport is not None`.

- [ ] **Step 4: Implement capability contracts and fail-closed consumers**

Create the shared dataclass/error/helper, advertise explicit capabilities from each transport, preflight in `upload_cloud`, classify the typed refusal as definite, and centralise CloudView upload enablement/reason text through the helper.

- [ ] **Step 5: Verify Cloud behaviour**

Run: `QT_QPA_PLATFORM=offscreen /home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_cloud_transaction.py tests/test_steam_backend.py tests/test_steam_cdp.py tests/test_steam_native_subprocess.py tests/test_ui_cloud.py -q`

Expected: PASS with no live Steam write.

- [ ] **Step 6: Commit**

```bash
git add editor/cloud_capabilities.py editor/transactions.py steam_cloud.py editor/steam_cdp.py editor/steam_native.py ui/cloud_view.py tests/test_cloud_transaction.py tests/test_steam_backend.py tests/test_steam_cdp.py tests/test_steam_native_subprocess.py tests/test_ui_cloud.py
git commit -m "fix: make Steam Cloud write capability explicit"
```

### Task 3: Redirect-safe and commit-safe updater

**Files:**
- Modify: `editor/updater.py`
- Modify: `tests/test_updater.py`

**Interfaces:**
- Consumes: `UpdateClient._open`, `_validate_url`, and `replace_installation`.
- Produces: redirect validation before I/O and a replacement commit point after which cleanup cannot roll back.

- [ ] **Step 1: Add a failing redirect integration test**

Run two local HTTP servers.  The allowed server redirects to a disallowed hostname backed by the second server.  Assert `ManifestError` and zero requests at the target.

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_updater.py -q`

Expected: FAIL because urllib follows the redirect before final URL validation.

- [ ] **Step 2: Add a failing post-commit cleanup test**

Monkeypatch only deletion of the backup tree to raise `OSError` after the new executable launches.  Assert `replace_installation` returns the new root, the new executable remains, and the old backup remains recoverable.

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_updater.py -q`

Expected: FAIL because cleanup failure currently enters rollback and restores the old tree.

- [ ] **Step 3: Implement validated redirect handling and cleanup separation**

Use a policy-aware `HTTPRedirectHandler` in an opener owned by `UpdateClient`.  Move backup deletion outside the rollback try/except and make only that cleanup best-effort.

- [ ] **Step 4: Verify updater tests**

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_updater.py tests/test_update_manifest.py tests/test_ui_updates.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add editor/updater.py tests/test_updater.py
git commit -m "fix: harden updater redirects and replacement commit"
```

### Task 4: Atomic Worker/R2/GitHub publication

**Files:**
- Modify: `.github/workflows/build.yml`
- Modify: `tests/test_ci_contract.py`
- Modify: `tools/publish_release.py`
- Modify: `tests/test_release_publish.py`

**Interfaces:**
- Consumes: final native artifacts and Cloudflare credentials.
- Produces: one prepared release directory uploaded and read back before the same bytes are attached to GitHub.

- [ ] **Step 1: Add failing workflow contract tests**

Require a credentials gate that fails when either Cloudflare secret is absent, prohibit warning-only continuation, require `Prepare stable release files` exactly once, and require R2 verification before GitHub release creation.

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_ci_contract.py -q`

Expected: FAIL because missing credentials currently skip R2 and continue to GitHub publication.

- [ ] **Step 2: Add a failing prepared-directory publication test**

Assert the R2 uploader accepts the already prepared stable directory and does not regenerate `latest.json` between R2 and GitHub consumers.

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_release_publish.py -q`

Expected: FAIL if the current API cannot publish one prepared set without rebuilding it.

- [ ] **Step 3: Implement the atomic workflow**

Add an early credential validation step, remove conditional skip/warning steps, prepare once, upload/verify that directory, then create/update GitHub Release from it.  Keep public read-back mandatory.

- [ ] **Step 4: Verify release contracts**

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_ci_contract.py tests/test_release_publish.py tests/test_update_manifest.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/build.yml tools/publish_release.py tests/test_ci_contract.py tests/test_release_publish.py
git commit -m "fix: publish release channels atomically"
```

### Task 5: Concurrent browser bootstrap with deferred catalog

**Files:**
- Create: `web/bootstrap.js`
- Create: `tests/js/web-bootstrap.test.mjs`
- Create: `tests/test_web_bootstrap_runtime.py`
- Modify: `web/app.js`
- Modify: `web/index.html`

**Interfaces:**
- Consumes: Pyodide URL, ooz URL, `pysrc.json`, `web_bridge.py`, and `catalogs.json`.
- Produces: `loadCoreResources(...)` and `installCatalogs(...)`; `state.catalogsReady` awaited by `openFile`.

- [ ] **Step 1: Add a failing Node behaviour test**

The test uses deferred fake imports/fetches to prove decoder import, Pyodide import, source fetch, and bridge fetch all start before any resolves; it also proves catalog fetch is absent from core resources and is separately awaited.

Run: `node --test tests/js/web-bootstrap.test.mjs`

Expected: FAIL because `web/bootstrap.js` does not exist.

- [ ] **Step 2: Add the pytest runtime bridge**

Add `tests/test_web_bootstrap_runtime.py` to invoke `node --test` when Node is available and skip with an explicit reason otherwise, so hosted runners exercise the real JavaScript module.

Run: `/home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_web_bootstrap_runtime.py -q`

Expected: FAIL until the bootstrap module is implemented.

- [ ] **Step 3: Implement and integrate bootstrap module**

Implement the two exported functions, change `app.js` to start core dependencies concurrently, enable the picker after bridge installation, start catalog installation in the background, and await `state.catalogsReady` before analysis.

- [ ] **Step 4: Verify browser runtime and generated delivery**

Run: `node --test tests/js/web-bootstrap.test.mjs && node --check web/app.js && /home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests/test_web_bootstrap_runtime.py tests/test_web_bridge.py -q && PYTHON=/home/dmytro/Projects/save-editor/.venv/bin/python make docs-check`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/bootstrap.js web/app.js web/index.html tests/js/web-bootstrap.test.mjs tests/test_web_bootstrap_runtime.py web/pysrc.json web/theme.css
git commit -m "perf: unblock browser startup from catalogs"
```

### Task 6: Proven dead-code and maintainability cleanup

**Files:**
- Modify: `editor/steam_native.py`
- Modify: `editor/platforms.py`
- Modify: `editor/xray_catalog.py`
- Modify: `editor/xray_save.py`
- Modify: `save_format.py`
- Modify: affected tests and generated `web/pysrc.json`

**Interfaces:**
- Consumes: repository-wide references, `__all__` exports, CLI entry points, and generated browser bundle.
- Produces: a smaller source tree with no removed callable referenced by runtime/tests/docs.

- [ ] **Step 1: Prove candidates have no consumers**

Run repository-wide `rg` searches for `_selected_release_ids`, `gog_roots`, `xbox_roots`, `_read_uncompressed_xdb`, `_parse_actor_state`, `scalar_candidates`, `patch_money`, and `patch_stack_count`; inspect exports and documentation for each.

Expected: each removable candidate has only its definition and no compatibility contract; any candidate with a contract is retained and recorded as a ruling.

- [ ] **Step 2: Remove proven dead definitions and unused imports**

Remove the unused future-framing `base64` import and only the definitions proven unconsumed in Step 1.  Rebuild generated browser sources.

- [ ] **Step 3: Run focused and full static checks**

Run: `PYTHON=/home/dmytro/Projects/save-editor/.venv/bin/python make web && PYTHON=/home/dmytro/Projects/save-editor/.venv/bin/python make check`

Expected: PASS with generated files current.

- [ ] **Step 4: Commit**

```bash
git add editor/steam_native.py editor/platforms.py editor/xray_catalog.py editor/xray_save.py save_format.py web/pysrc.json
git commit -m "refactor: remove unreferenced editor code"
```

### Task 7: Release documentation, version, and complete verification

**Files:**
- Modify: `VERSION`
- Modify: `README.md`
- Modify: `docs/STATUS.md`
- Modify: release/evidence documentation selected by existing project convention.

**Interfaces:**
- Consumes: all prior task contracts and release artifact naming.
- Produces: version `0.5.17`, truthful user-facing notes, verified source and Linux artifacts ready for hosted Windows build.

- [ ] **Step 1: Update version and documentation**

Set `VERSION` to `0.5.17`.  Document read-only Cloud fallback, definite versus uncertain write failures, atomic release requirements, updater behaviour, browser startup, and remaining external game-validation gates.

- [ ] **Step 2: Run complete source verification**

Run: `PYTHON=/home/dmytro/Projects/save-editor/.venv/bin/python make check && /home/dmytro/Projects/save-editor/.venv/bin/python -m mypy --platform win32 && /home/dmytro/Projects/save-editor/.venv/bin/python -m pytest tests -q && node --test tests/js/web-bootstrap.test.mjs && node --check web/app.js`

Expected: all checks pass with zero failures.

- [ ] **Step 3: Build and smoke Linux artifacts**

Run: `PYTHON=/home/dmytro/Projects/save-editor/.venv/bin/python make package`

Expected: Linux portable tarball, Debian package, and checksums for `0.5.17` are produced successfully; packaged diagnostic exits zero.

- [ ] **Step 4: Audit the final tree**

Run Git diff whitespace checks, tracked-private-file scan, dead-symbol search, package plan, dependency check, and clean generated-file checks.  Review every changed file and record any ruling or deferred minor.

Expected: no unaccounted generated output, private inputs, or temporary files.

- [ ] **Step 5: Commit**

```bash
git add VERSION README.md docs web
git commit -m "release: prepare v0.5.17 hardening"
```

### Task 8: Hosted integration, release, deployment, and cleanup

**Files:**
- No product source changes unless hosted verification exposes a regression.

**Interfaces:**
- Consumes: verified branch commits and `v0.5.17` release workflow.
- Produces: integrated main, green hosted matrix, release assets, matching R2/Worker/Pages state, protected main, and cleaned obsolete branch/worktree state.

- [ ] **Step 1: Complete whole-branch review**

Generate the review package from merge base through HEAD and run a fresh-context review.  Fix every Critical/Important finding through RED -> GREEN and rerun the suite.

- [ ] **Step 2: Integrate and push the verified branch**

Fast-forward or merge into `main` without force, rerun the complete suite on the integrated tree, then push `main`.

- [ ] **Step 3: Verify hosted main matrix**

Wait for Linux and Windows Python 3.11/3.12 jobs.  All four jobs must pass source gate and pytest before release tagging.

- [ ] **Step 4: Tag and monitor `v0.5.17`**

Create and push the annotated tag only from the verified main SHA.  Wait for Linux/Windows package, diagnostics, installer smoke, Worker deployment, R2 upload/read-back, and GitHub release jobs.

- [ ] **Step 5: Deploy and verify Pages**

Deploy generated `web/` from the release SHA.  Verify Pages returns 200 and its download links match the public R2 files.

- [ ] **Step 6: Protect main and clean obsolete state**

Require the hosted test matrix on `main` where the repository plan permits it.  Review unique commits on stale `codex/*` branches, delete only superseded branches, retain independent `gh-pages`, remove the completed worktree/feature branch, and run retention-aware Git garbage collection.

- [ ] **Step 7: Final public read-back**

Compare GitHub and Worker `latest.json` byte-for-byte, verify every advertised size/SHA-256 by public download, and confirm the application update client reports `0.5.17` from `0.5.16`.

Expected: one version and one byte set across application, GitHub, R2, Worker, and Pages.
