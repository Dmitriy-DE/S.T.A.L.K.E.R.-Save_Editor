# Maintainability and Distribution Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Each task is independently testable and reviewable.

**Goal:** Make the repository safer, simpler to maintain, and releasable by an unrelated developer without weakening save or Steam Cloud safety.

**Architecture:** Keep the existing shared Python core and Qt/web/CLI surfaces. Consolidate release metadata and mutation maturity into existing small data models, move only proven responsibilities out of god modules, and keep Cloudflare Worker/R2 as the public download and diagnostics boundary. Use a signed APT repository as an additional Linux package channel; direct `.deb` downloads remain available.

**Tech Stack:** Python 3.11+, PySide6, pytest, Ruff, mypy, PyInstaller, Debian `dpkg-deb`, AppStream metainfo, Cloudflare Workers/R2, GitHub Actions.

**Spec:** User-supplied maintainability, security, Debian distribution, release, and documentation audit pasted on 2026-09-21.

## Global Constraints

- Preserve backup, source SHA, CRC/framing, immutable preview, atomic replacement, read-back verification, and fail-closed unknown-format behavior.
- Steam Cloud writes remain explicit; uncertain native writes are never automatically retried.
- No guessed parser offsets, SID mappings, serializer shapes, or game-acceptance claims.
- No new framework, DI container, event bus, repository layer, or generic manager unless it removes more code than it adds.
- No personal saves, credentials, Steam session material, or user-specific paths in Git.
- No public version bump until every phase and final gate is green.
- Do not perform real Steam Cloud writes in CI.

## Review Focus

- Credential-bearing log lines must lose the complete value, including Bearer/basic schemes, cookie values, and URL query secrets.
- Public diagnostics must remain bounded, POST-only, unreadable, and rate-limited without embedding a secret in the desktop binary.
- Every official release must resolve through the same registry for local discovery, Cloud, UI selection, and app IDs.
- Qt, web, and CLI must receive the same maturity decision for every mutation capability.
- A package installed from the repository must have valid Debian/AppStream metadata and discover a later package through APT.

### Task 1: Diagnostics security and retention

**Files:** `editor/diagnostics.py`, `infra/downloads-worker/worker.js`, `infra/downloads-worker/wrangler.toml`, diagnostics/Worker tests, release/deployment docs.

- Add failing redaction tests for headers, cookie/token/password values, URL query secrets, Linux/Windows home paths, and save-byte exclusion.
- Replace the leaking regex with a small ordered redaction pass that consumes complete credential values and preserves only safe parameter names.
- Add failing Worker tests for scheduled retention, bounded body handling, rejected read access, and rate-limit configuration/behavior.
- Move retention out of every POST into scheduled cleanup or a supported R2 lifecycle mechanism; keep POST O(1) with respect to stored reports.
- Add the simplest Cloudflare-side rate-limit binding/configuration available for this Worker and document its deployment requirement; do not add client authentication secrets.
- Run focused tests, `node --check`, `make check`, and the complete suite; commit and request review.

### Task 2: Single release registry and single capability model

**Files:** `editor/releases.py`, `editor/steam_profiles.py`, `editor/platforms.py`, `editor/equipment.py`, `editor/capabilities.py`, format/service bridges, affected Qt/web/CLI/tests.

- Add failing invariant tests covering unique official IDs, app ownership, local/cloud lookup parity, and release traits.
- Extend the existing immutable release model only with data genuinely owned by a release; derive profiles and discovery maps from it.
- Remove duplicated app-ID/release sets after all callers use the registry.
- Add failing capability tests for all mutation surfaces and all four maturity states.
- Make legacy booleans computed projections of the maturity result and remove independently editable duplicate state.
- Prove identical capability serialization for Qt, web, and CLI; preserve unknown/read-only behavior.
- Run full tests and type/docs gates; commit and request review.

### Task 3: Targeted maintainability/dead-code pass

**Files:** only responsibility-boundary modules and their tests; likely `ui/main_window.py`, `editor/platforms.py`, `editor/xray_save.py`, `save_format.py`, and small new focused modules when a split removes duplication.

- Capture symbol/reference evidence before deleting anything; include dynamic entry points, PyInstaller hidden imports, browser bundle inputs, and research tools.
- Extract only coherent UI-free use cases and platform responsibilities; do not rewrite binary codecs for line count.
- Remove verified obsolete wrappers, aliases, duplicated constants, unreachable branches, stale comments, and unused imports.
- Add regression tests before each behavior change and run the full suite after each bounded extraction.
- Reduce active docs to product/architecture/release/evidence/current research; move useful historical handoffs/plans/task cards to `docs/history` and remove generated machinery only after repository references are gone.

### Task 4: Debian/AppStream/APT and reproducible release

**Files:** `packaging/build.py`, packaging assets, `infra/downloads-worker/`, release tools/workflows, package tests, `README.md`, `CONTRIBUTING.md`, release docs.

- Add failing package tests for Maintainer/Homepage/license/description/Installed-Size, desktop ID, icons, metainfo, and accurate `Depends` baseline.
- Add AppStream metainfo and validate it with `appstreamcli`; add `lintian` to Linux CI and run it with an explicit policy for non-fatal informational tags.
- Build against an explicit oldest supported glibc baseline (Ubuntu 22.04-compatible if retained) and document the supported floor; do not derive it from the current workstation.
- Add signed `dists/<distribution>/...` and `pool/` repository generation, publish metadata/package through R2, and verify it in a disposable APT source with `apt update`/upgrade discovery.
- Add CI secret preflight, signing-key handling, stable artifact publication, public read-back, GitHub Release, and APT publication in one tag flow; fail before partial claims when credentials are absent.
- Keep direct `.deb` and portable downloads working.

### Task 5: Final audit and release

- Re-run duplicate-registry/capability searches, dead-code evidence, exception/blocking/read bounds, source-path and generated-file checks, package/update parity, and unsupported-claim scans.
- Record before/after LOC/module/docs/registry/capability/test/package evidence.
- Run `make check`, `make test`, `node --check web/app.js`, `git diff --check`, Linux package/diagnostic/AppStream/lintian/APT smoke, hosted Windows portable/installer/upgrade smoke, and browser drift/runtime gates.
- Request an independent code review, fix all actionable findings, then create the only final public version/tag after the merged tree is green.
