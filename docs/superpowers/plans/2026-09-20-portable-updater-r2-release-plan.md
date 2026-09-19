# Portable Builds, R2 Releases, and In-App Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship native Windows/Linux portable artifacts, publish exact release bytes to GitHub Releases and Cloudflare R2, and add safe cross-platform in-app update checks and installation.

**Architecture:** Keep release metadata in one stdlib-only manifest module. The build/publish path generates the manifest from final artifacts and uploads the same bytes to GitHub and R2. The desktop UI consumes a platform-neutral updater service; a separate frozen updater executable performs replacement after the GUI exits, while Debian updates hand off to the package manager.

**Tech Stack:** Python 3.11/3.12, PySide6, PyInstaller, pytest, ruff, mypy, GitHub Actions, Wrangler/R2, existing Cloudflare Worker.

**Spec:** `docs/superpowers/specs/2026-09-20-portable-updater-r2-release-design.md`

## Global Constraints

- Portable targets are native Windows x86_64 ZIP and Linux x86_64 tar.gz; PyInstaller is not cross-compiled.
- The existing Linux amd64 `.deb` remains a published package and uses an explicit package-manager handoff for updates.
- `latest.json` is generated from final artifact bytes and contains size plus lowercase SHA-256 for every artifact.
- The updater uses only Python standard-library runtime code and never executes an unverified download.
- Failed checks/downloads/replacements leave the current installation usable.
- Source tests remain credential-free and read-only; only the release publication job receives R2/GitHub write credentials.
- Personal saves, backups, credentials, `.git`, and build caches never enter release artifacts.
- Existing parser/save semantics remain unchanged unless a release/update regression requires a targeted fix.
- Every production function added or changed gets a behavior test written and observed failing before implementation.

## Review Focus

- A manifest for another platform must never be offered by the current installation; tested in manifest selection tests.
- A valid-size but wrong-byte download must be rejected before extraction; tested in hash verification tests.
- A running portable installation must not be replaced in-process; tested in updater staging/parent-wait tests.
- A failed rename or first launch must restore the previous installation; tested in rollback tests.
- R2 and GitHub must receive identical artifact bytes and the release must fail on read-back mismatch; tested in publication contract/read-back tests.

---

### Task 1: Add manifest and release-artifact primitives

**Files:**
- Create: `editor/update_manifest.py`
- Create: `tools/build_release_manifest.py`
- Test: `tests/test_update_manifest.py`
- Test: `tests/test_release_manifest_tool.py`
- Modify: `editor/__init__.py` only if the package exports public update types

**Interfaces:**
- `editor.update_manifest.ReleaseManifest.from_json(payload: str) -> ReleaseManifest`
- `editor.update_manifest.ReleaseManifest.select(target: str, architecture: str = "x86_64") -> ArtifactSpec`
- `editor.update_manifest.ArtifactSpec.verify(path: Path) -> None`
- `editor.update_manifest.compare_versions(current: str, latest: str) -> int`
- `tools/build_release_manifest.py --version VERSION --commit SHA --artifact PATH ... --output latest.json`

- [ ] **Step 1: Write failing manifest tests**

  Cover schema validation, stable target selection, strict version comparison, malformed SHA/size rejection, URL host allow-listing, and artifact verification failure.

- [ ] **Step 2: Run the focused tests and confirm the expected missing-interface failures**

  Run: `.venv/bin/python -m pytest tests/test_update_manifest.py tests/test_release_manifest_tool.py -q`

  Expected: collection or assertion failures because the new manifest module and CLI do not exist yet.

- [ ] **Step 3: Implement the minimal typed manifest model**

  Use frozen dataclasses, `json.loads`, exact schema checks, lowercase hexadecimal SHA validation, non-negative integer sizes, HTTPS R2 host validation, and a deterministic version comparator supporting the repository's numeric dotted versions.

- [ ] **Step 4: Implement the manifest generator**

  Read each artifact once for size and SHA-256, require all three release artifact kinds, take commit/version from explicit arguments, emit stable sorted JSON, and reject missing or private inputs.

- [ ] **Step 5: Run focused tests and the full suite**

  Run: `.venv/bin/python -m pytest tests/test_update_manifest.py tests/test_release_manifest_tool.py -q` and then `.venv/bin/python -m pytest tests -q`.

- [ ] **Step 6: Commit the self-contained release-contract change**

  Run: `git add editor/update_manifest.py tools/build_release_manifest.py tests/test_update_manifest.py tests/test_release_manifest_tool.py && git commit -m "feat: add verified release manifest contract"`

### Task 2: Add safe updater staging and replacement

**Files:**
- Create: `editor/updater.py`
- Create: `packaging/updater_entry.py`
- Modify: `packaging/editor.spec`
- Modify: `packaging/build.py`
- Test: `tests/test_updater.py`
- Test: `tests/test_packaging.py`

**Interfaces:**
- `editor.updater.UpdateClient.check() -> UpdateCheckResult`
- `editor.updater.UpdateClient.download(artifact: ArtifactSpec, destination: Path) -> Path`
- `editor.updater.detect_installation() -> InstallationInfo`
- `editor.updater.stage_archive(archive: Path, installation: InstallationInfo, staging_root: Path) -> Path`
- `editor.updater.build_update_command(...) -> list[str]`
- `packaging.updater_entry.main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write failing updater tests**

  Use a local HTTP server and temporary directories to test current-version result, available update result, timeout/unavailable result, corrupt hash rejection, exact-size rejection, target selection, ZIP/tar extraction, expected executable validation, parent-process wait arguments, and rollback after failed replacement.

- [ ] **Step 2: Run updater tests and confirm RED**

  Run: `.venv/bin/python -m pytest tests/test_updater.py -q`

  Expected: failures for missing updater types/functions, not fixture or network errors.

- [ ] **Step 3: Implement the dependency-free updater client**

  Stream `urllib.request` responses to a temporary file, enforce connect/read/total bounds, compute SHA-256 while writing, reject non-R2 hosts and redirects outside the allow-list, and clean temporary files on every failure.

- [ ] **Step 4: Implement platform installation detection and archive staging**

  Identify frozen Windows/Linux portable installations from `sys.executable` and `BUILD_MANIFEST.json`; recognize Debian installs from `/usr/lib/stalker2-save-editor`; extract only the expected top-level `SaveEditor/` tree; reject path traversal and missing `SaveEditor` executable/manifest.

- [ ] **Step 5: Implement the external replacement process**

  Add the updater entry point to the PyInstaller analysis and collection. It waits for the parent PID, stages beside the installation, renames the current directory to a recoverable backup, installs the staged tree, starts the new executable, and restores the backup if launch or rename fails.

- [ ] **Step 6: Extend packaging tests**

  Assert the frozen spec includes `SaveEditor-updater`, both target archives contain it, and private/save files remain rejected.

- [ ] **Step 7: Run focused and full tests**

  Run: `.venv/bin/python -m pytest tests/test_updater.py tests/test_packaging.py -q` and then `.venv/bin/python -m pytest tests -q`.

- [ ] **Step 8: Commit the updater core**

  Run: `git add editor/updater.py packaging/updater_entry.py packaging/editor.spec packaging/build.py tests/test_updater.py tests/test_packaging.py && git commit -m "feat: add safe portable update staging"`

### Task 3: Integrate update checks into Qt without blocking the UI

**Files:**
- Create: `ui/update_dialog.py`
- Modify: `ui/main_window.py`
- Modify: `ui/support_dialog.py` or `ui/settings_view.py` following the existing surface that owns support/settings actions
- Modify: `ui/theme.py` only for update-state styling
- Test: `tests/test_ui_updates.py`

**Interfaces:**
- `ui.update_dialog.UpdateWorker`
- `ui.update_dialog.UpdateDialog`
- `MainWindow.check_for_updates(manual: bool = False) -> None`

- [ ] **Step 1: Write failing UI tests**

  Cover startup background check, manual check, current version, update available, unavailable network, download cancellation, and no UI mutation from a worker thread.

- [ ] **Step 2: Run the UI tests and confirm RED**

  Run: `.venv/bin/python -m pytest tests/test_ui_updates.py -q`

- [ ] **Step 3: Implement the worker and typed result handling**

  Inject the updater client for tests, emit only immutable results, keep the main window responsive, and suppress noisy startup errors while showing actionable manual-check errors.

- [ ] **Step 4: Add the update dialog and action**

  Show current/latest version, target, size, SHA verification status, and explicit `Скачать и обновить` / `Перезапустить` actions. Route `.deb` to the package-manager handoff and portable archives to the external updater.

- [ ] **Step 5: Run UI and full tests**

  Run: `.venv/bin/python -m pytest tests/test_ui_updates.py -q` and `.venv/bin/python -m pytest tests -q`.

- [ ] **Step 6: Commit the UI integration**

  Run: `git add ui/update_dialog.py ui/main_window.py ui/support_dialog.py ui/settings_view.py ui/theme.py tests/test_ui_updates.py && git commit -m "feat: add non-blocking update checks"`

### Task 4: Publish manifest and artifacts to GitHub Releases and R2

**Files:**
- Create: `tools/publish_release.py`
- Modify: `infra/downloads-worker/worker.js`
- Modify: `infra/downloads-worker/wrangler.toml` only if cache/metadata configuration needs it
- Modify: `.github/workflows/build.yml`
- Modify: `tests/test_ci_contract.py`
- Create: `tests/test_publish_release.py`
- Modify: `Makefile`

**Interfaces:**
- `tools/publish_release.py --artifacts DIR --version VERSION --commit SHA --output DIR --publish-r2`
- `make release-manifest ARTIFACT_DIR=...`
- `make r2-publish ARTIFACT_DIR=...`

- [ ] **Step 1: Write failing publication and CI-contract tests**

  Assert the generated manifest references exact local hashes, publication rejects missing artifacts, Wrangler commands use the configured bucket, the release workflow collects both native builds, and the worker gives JSON content type/no attachment disposition for `latest.json`.

- [ ] **Step 2: Run publication tests and confirm RED**

  Run: `.venv/bin/python -m pytest tests/test_publish_release.py tests/test_ci_contract.py -q`

- [ ] **Step 3: Implement deterministic local manifest/release preparation**

  Reuse the manifest model and generator, create stable-name copies from versioned artifacts without changing bytes, write `SHA256SUMS`, and support dry-run output containing the exact upload plan.

- [ ] **Step 4: Extend the worker response policy**

  Return `latest.json` with `application/json`, short cache control, and inline disposition; keep binary files as attachments and preserve the existing 404/405 behavior.

- [ ] **Step 5: Extend the tag workflow**

  Give only the tag release job `contents: write`, collect Linux and Windows artifacts, generate the manifest, create/update the GitHub Release, upload assets, publish stable objects with Wrangler using GitHub secrets, and read each public R2 URL back to compare status, size, and SHA-256.

- [ ] **Step 6: Add explicit Make targets and local dry-run guards**

  Keep normal `make check` credential-free. Require an explicit publication flag and fail closed if the artifact directory contains private files or a dirty source manifest.

- [ ] **Step 7: Run CI-contract and full tests**

  Run: `.venv/bin/python -m pytest tests/test_publish_release.py tests/test_ci_contract.py -q` and then `.venv/bin/python -m pytest tests -q`.

- [ ] **Step 8: Commit the publication pipeline**

  Run: `git add tools/publish_release.py infra/downloads-worker/worker.js .github/workflows/build.yml tests/test_ci_contract.py tests/test_publish_release.py Makefile && git commit -m "feat: publish releases through GitHub and R2"`

### Task 5: Update documentation and run the code-quality pass

**Files:**
- Modify: `README.md`
- Modify: `docs/RELEASE.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/evidence/CI_AND_WINDOWS_2026-09-14.md` or a new dated evidence file
- Modify: `THIRD_PARTY_NOTICES.md` only if updater/runtime packaging changes notices
- Test: `tests/test_docs_consistency.py`

- [ ] **Step 1: Write failing documentation-contract assertions**

  Assert README commands and release docs name Windows/Linux portable artifacts, `latest.json`, R2 read-back, update limitations, and the exact distinction between local verification and hosted release evidence.

- [ ] **Step 2: Run the documentation tests and confirm RED**

  Run: `.venv/bin/python -m pytest tests/test_docs_consistency.py -q`

- [ ] **Step 3: Update docs with current commands and evidence boundaries**

  Document portable startup, manual update behavior, `.deb` handoff, R2/GitHub publication, required secrets, and unverified Windows visual/privileged install gates. Do not claim hosted release success until the actual workflow and public URLs are checked.

- [ ] **Step 4: Perform focused simplification review**

  Search for duplicate version readers, repeated R2 URLs, ad-hoc checksum code, stale release claims, unused updater branches, and dead imports in affected files. Consolidate only changes covered by tests; do not refactor save parsers opportunistically.

- [ ] **Step 5: Run the full local quality gate**

  Run: `make test PYTHON=.venv/bin/python` and `make check PYTHON=.venv/bin/python`.

- [ ] **Step 6: Commit docs and cleanup**

  Run: `git add README.md docs/RELEASE.md docs/STATUS.md docs/evidence tests/test_docs_consistency.py THIRD_PARTY_NOTICES.md && git commit -m "docs: document portable updates and release gates"`

### Task 6: Build, publish, and verify the release

**Files:**
- Modify: `VERSION` only when the release version is intentionally advanced for this feature
- Generated/untracked: `dist/` and temporary release staging outside the source tree
- Evidence: `docs/RELEASE.md`, `docs/STATUS.md`

- [ ] **Step 1: Re-read the plan and inspect clean Git state**

  Run: `git status --short --branch` and confirm no personal saves, `.local`, credentials, or unrelated edits are present.

- [ ] **Step 2: Run the full local tests and checks before packaging**

  Run: `make test PYTHON=.venv/bin/python` and `make check PYTHON=.venv/bin/python`.

- [ ] **Step 3: Build Linux portable and `.deb` artifacts locally**

  Run: `.venv/bin/python packaging/build.py --target linux --output-dir dist` and verify `SHA256SUMS`, `BUILD_MANIFEST.json`, diagnostic startup, archive contents, and private-file scan.

- [ ] **Step 4: Verify Windows build path through the hosted runner**

  Run the tag/manual build workflow, inspect the Windows packaged diagnostic result, and do not call Windows desktop UI or updater behavior locally verified unless the runner/manual evidence exists.

- [ ] **Step 5: Publish only after build gates are green**

  Create/update the intended version tag/release only if the repository's existing release policy and user-authorized publication state allow it. Upload exact assets to GitHub and R2 through the release job; never upload a dirty local build as stable.

- [ ] **Step 6: Read back public R2 and web links**

  Fetch `latest.json` and all artifact URLs through the public Worker, compare HTTP status, content length, and SHA-256 against the manifest and GitHub assets.

- [ ] **Step 7: Run final verification and report exact evidence**

  Run `git diff --check`, `git status --short --branch`, full tests/checks if any final docs change occurred, and report commit SHA, artifacts, hashes, R2 read-back, hosted workflow status, and remaining external gates without overclaiming.
