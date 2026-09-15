# Official S.T.A.L.K.E.R. Save Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one Qt desktop editor and one static browser editor for the four official S.T.A.L.K.E.R. game families, with original and verified Enhanced Edition profiles, automatic/manual desktop save discovery, shared parsing/writing, and evidence-backed inventory edits.

**Architecture:** Keep `EditorService` and the format registry as the only mutation/parser boundary. Represent each official release/build as a profile containing detection, inspection, capabilities, catalog resolution, and immutable edit preparation; Qt and web render the same snapshots and capability flags. Discovery remains read-only, browser input remains local-file-only, and every writer uses source SHA, no-op preservation, strict reparse, and output-copy safeguards.

**Tech Stack:** Python 3.11+, PySide6/Qt, pytest, ruff, mypy, Pyodide, vanilla JavaScript, existing LZO/Kraken/CRC codecs, installed official game resources read-only, and the existing atomic backup/export/storage layer.

**Spec:** `docs/superpowers/specs/2026-09-15-official-stalker-editor-design.md`

## Global Constraints

- Official PC releases only; community mods and mod-specific builds are out of scope.
- The desktop may read installed official game data read-only; game binaries, private saves, credentials, and personal catalogs never enter Git.
- Browser security prevents folder scanning; web accepts local files and downloads new copies only.
- Unknown versions, unknown formats, missing catalogs, and unproven fields fail closed and remain visible as read-only.
- No automatic Steam writes, restore, or real-game slot overwrite.
- Preserve CRC, decompression, no-op SHA, source SHA, backup, atomic export, persistence/read-back, and strict round-trip safeguards.
- Do not infer a field from one matching save, a filename extension, a type-key coincidence, or a guessed registry boundary.
- Every production change starts with a failing behavioral test, then minimal implementation, then the relevant full gate.
- Do not claim Enhanced, Windows, cloud, deployment, or in-game validation until the matching evidence exists.

---

## Current Baseline and File Map

The current branch already contains the S.T.A.L.K.E.R. 2 adapter, original
SoC/CS/CoP X-Ray container/reader, manual save paths, slot discovery, Qt/web
bridges, and a limited money/ammo writer. These are starting points, not proof
that the full goal is complete.

Create or modify only the following focused units unless a test failure proves
another boundary is required:

- `editor/releases.py` — public official-release descriptors, aliases, and
  release-to-format mapping.
- `editor/capabilities.py` — immutable capability flags shared by Qt and web.
- `editor/catalog.py` — catalog interfaces and source-independent item
  definitions.
- `editor/xray_catalog.py` — read-only extraction of official X-Ray item data
  from an explicitly selected game installation.
- `editor/xray_save.py` and `editor/xray_container.py` — X-Ray parser,
  object registry model, and fixed/length-changing writers.
- `editor/formats.py`, `editor/service.py`, `editor/models.py` — shared
  registry, immutable plans, and orchestration.
- `editor/platforms.py`, `editor/settings.py` — official release discovery and
  manual path persistence.
- `ui/main_window.py`, `ui/save_slots_view.py`, `ui/settings_view.py`,
  `ui/inventory_view.py`, `ui/inventory_model.py` — release selection,
  candidate rows, capabilities, and staged edits.
- `web/web_bridge.py`, `web/app.js`, `web/index.html` — the same snapshot,
  capability flags, and local-file/download surface.
- `tests/test_releases.py`, `tests/test_capabilities.py`,
  `tests/test_catalog.py`, `tests/test_xray_catalog.py`,
  `tests/test_xray_save.py`, `tests/test_formats.py`,
  `tests/test_platform_save_locations.py`, `tests/test_save_slots.py`,
  `tests/test_ui_*.py`, `tests/test_web_bridge.py` — behavior and regression
  coverage.
- `docs/evidence/`, `docs/tasks/`, `docs/STATUS.md`, `README.md`, and the
  generated `web/pysrc.json` — evidence and user-facing status only after
  runtime behavior is verified.

## Task 1: Official release descriptors and capability contract

**Files:**

- Create: `editor/releases.py`
- Create: `editor/capabilities.py`
- Modify: `editor/formats.py`, `editor/models.py`, `editor/service.py`
- Test: `tests/test_releases.py`, `tests/test_capabilities.py`,
  `tests/test_formats.py`, `tests/test_service.py`

**Interfaces:**

- `ReleaseDescriptor(id: str, family: str, edition: str, title: str, app_ids: tuple[int, ...], extensions: frozenset[str])`
- `official_releases() -> tuple[ReleaseDescriptor, ...]`
- `release_by_id(release_id: str) -> ReleaseDescriptor`
- `FormatCapabilities(read_inventory: bool, edit_money: bool, edit_stacks: bool, move_items: bool, add_items: bool, remove_items: bool, edit_durability: bool, edit_upgrades: bool, catalog: bool)`
- Every registered `SaveFormat` exposes `release_id`, `edition`, `capabilities`, `detect`, `inspect`, and `prepare`.

- [x] **Step 1: Write failing registry tests.** Assert that the registry
  returns exactly the S.T.A.L.K.E.R. 2, original SoC/CS/CoP, and reserved
  Enhanced release descriptors; duplicate IDs and unknown aliases fail with a
  stable exception. Assert that existing S2 and X-Ray adapters expose explicit
  capability flags instead of UI guessing from format IDs.
- [x] **Step 2: Run the targeted tests and verify the expected missing-symbol
  failures.** Run:
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_releases.py tests/test_capabilities.py tests/test_formats.py -q`.
- [x] **Step 3: Implement the descriptor and capability dataclasses.** Keep
  the existing format IDs stable for CLI/web compatibility, add release/edition
  metadata to adapters, and mark current X-Ray money/ammo support accurately.
- [x] **Step 4: Run the targeted tests and the service tests.** Confirm unknown
  bytes still produce structured detection failures and existing S2 behavior
  is unchanged.
- [x] **Step 5: Commit the contract independently.** Use:
  `git add editor/releases.py editor/capabilities.py editor/formats.py editor/models.py editor/service.py tests/test_releases.py tests/test_capabilities.py tests/test_formats.py tests/test_service.py && git commit -m "feat: add official release capability contract"`.

## Task 2: Release-aware desktop discovery and manual selection

**Files:**

- Modify: `editor/platforms.py`, `editor/settings.py`,
  `ui/save_slots_view.py`, `ui/settings_view.py`, `ui/main_window.py`
- Test: `tests/test_platform_save_locations.py`, `tests/test_settings.py`,
  `tests/test_save_slots.py`, `tests/test_ui_theme.py`

**Interfaces:**

- `installed_releases(...) -> tuple[InstalledGame, ...]` returns one
  deduplicated official release descriptor per app manifest and install tree.
- `save_search_paths(release_id: str, ...) -> tuple[Path, ...]` and
  `manual_save_search_paths(release_id: str, ...) -> tuple[Path, ...]` keep
  existing path compatibility while accepting release IDs.
- `SaveSlot` carries `candidate_release_id`, `detected_release_id`, and a
  structured unsupported reason.

- [x] **Step 1: Write failing tests for release-specific search.** Cover two
  installed originals with the same family name, Enhanced candidate roots,
  duplicate Steam libraries, `.sav/.scop/.scs` candidates, manual-root
  priority, and no directory creation.
- [x] **Step 2: Run only those tests and verify the baseline fails on the new
  release-specific fields or `.scs` behavior.**
- [x] **Step 3: Implement descriptor-driven path resolution.** Preserve the
  existing Windows registry, Steam VDF, Proton, Documents, `_appdata_`,
  `fsgame.ltx`, and S.T.A.L.K.E.R. 2 package providers; deduplicate by resolved
  release/path and never attribute a file from a path name alone.
- [x] **Step 4: Add a desktop release selector and filter.** The selector must
  support “all official releases”, a specific game/edition, and manual folder
  selection. Discovery runs in the existing worker and uses `detect_fast`; an
  explicit open performs strict detection and full inspection.
- [x] **Step 5: Run Qt and platform tests.** Verify the search button remains
  responsive, paths remain visible, unsupported candidates remain visible, and
  a manual root does not silently merge with auto roots.
- [x] **Step 6: Commit the release-aware discovery slice.** Use:
  `git add editor/platforms.py editor/settings.py ui/save_slots_view.py ui/settings_view.py ui/main_window.py tests/test_platform_save_locations.py tests/test_settings.py tests/test_save_slots.py tests/test_ui_theme.py && git commit -m "feat: make desktop discovery release-aware"`.

## Task 3: Catalog interface and official X-Ray resource reader

**Files:**

- Create: `editor/catalog.py`, `editor/xray_catalog.py`
- Modify: `editor/platforms.py`, `editor/formats.py`, `editor/service.py`
- Test: `tests/test_catalog.py`, `tests/test_xray_catalog.py`,
  `tests/test_platform_save_locations.py`

**Interfaces:**

- `ItemDefinition(key: str, display_name: str | None, category: str | None, unit_weight: float | None, width: int | None, height: int | None, max_stack: int | None, slots: tuple[str, ...], prototype: bytes | None, source: str)`
- `ItemCatalog(release_id: str, source_root: Path | None, items: tuple[ItemDefinition, ...])`
- `CatalogProvider.load(release: ReleaseDescriptor, game_root: Path | None = None) -> ItemCatalog | None`
- `CatalogProvider.resolve(key: str) -> ItemDefinition | None`

- [x] **Step 1: Write failing catalog tests using tiny official-style text and
  packed fixtures.** Assert that keys, localization names, category, weight,
  stack rules, and prototype/source provenance are preserved; missing fields
  remain `None`; a missing or foreign root returns no catalog rather than
  inventing definitions.
- [x] **Step 2: Run the catalog tests and confirm the provider does not exist.**
- [x] **Step 3: Implement the source-independent catalog model and a strict
  X-Ray provider.** The provider reads only an explicit installed-game root,
  supports unpacked `gamedata` first, and uses a small provenance-reviewed
  reader for official packed archives where needed. It must not copy game
  archives or private files into the repository.
- [x] **Step 4: Implement localization and section resolution.** Resolve
  serialized keys from the save to official display names only when the selected
  release catalog proves the mapping; keep the original key visible beside the
  localized name.
- [x] **Step 5: Run fixture tests plus a read-only catalog inventory on the
  installed SoC/CS/CoP trees.** Record counts, missing metadata, and source
  roots without printing private paths or storing game data.
- [x] **Step 6: Commit the catalog boundary.** Use:
  `git add editor/catalog.py editor/xray_catalog.py editor/platforms.py editor/formats.py editor/service.py tests/test_catalog.py tests/test_xray_catalog.py tests/test_platform_save_locations.py && git commit -m "feat: add official X-Ray item catalogs"`.

## Task 4: Complete original X-Ray inventory model and writer

**Files:**

- Modify: `editor/xray_container.py`, `editor/xray_save.py`,
  `editor/models.py`, `editor/prepare.py`, `save_format.py`
- Test: `tests/test_xray_container.py`, `tests/test_xray_save.py`,
  `tests/test_web_bridge.py`, `tests/test_cli.py`
- Evidence: `docs/evidence/XRAY_INVENTORY_2026-09-15.md`

**Interfaces:**

- `parse_xray(..., with_inventory=True) -> XRaySave` returns every actor-owned
  object with a validated record span, object class/version, state/update
  packets, item key, ownership relation, and explicit unknown fields.
- `XRayItemAdd(handle: int | None, item_key: str, quantity: int, destination: str)`
  is an immutable add request resolved through `ItemCatalog`.
- `prepare_xray(data: bytes, plan: EditPlan, spec: XRayFormatSpec, catalog: ItemCatalog | None = None) -> PreparedEdit`
  supports only operations whose object serialization is proven.

- [ ] **Step 1: Write failing fixture tests for all original item families
  present in the real corpus:** weapons, armor/outfit, artifacts, devices,
  consumables, grenades, ammo, and unknown/extension objects. Assert full
  actor ownership, duplicate handles, record boundaries, and unknown fields are
  reported explicitly.
- [x] **Step 2: Run the tests and confirm the current parser only exposes
  partial names/categories and ammo counts.** Keep the red result as evidence
  that the new tests cover missing behavior.
- [x] **Step 3: Implement strict object-record indexing.** Parse the complete
  OBJECT chunk, retain raw spawn/state/update bytes for unchanged objects, and
  expose known offsets only after class/version checks. Never use a guessed end
  boundary for mutation.
- [ ] **Step 4: Add money, stack, move, and equipment operations only for fields
  with controlled evidence.** Each operation must validate parent/handle,
  ranges, duplicate requests, and source SHA before rebuilding.
- [x] **Step 5: Implement catalog-backed add/remove for the first proven class
  (ammo).** Allocate a fresh handle not present in the registry, validate the
  official catalog key/family, clone the matching same-save template, attach it
  to the actor, update registry count/framing, rebuild LZO, and strictly
  reparse. The test proves original bytes are unchanged and output contains
  both state and update counts.
- [x] **Step 6: Extend add/remove class-by-class only after a real controlled
  pair exists.** The local original corpus now exercises base, detector, outfit,
  PDA, torch, weapon, magazine, shotgun, WGL and ammo families. The writer
  remains closed for unknown families, missing templates and unproven game
  semantics; it does not copy prototype bytes from archives.
- [x] **Step 7: Run the real read-only corpus gate.** For every unique local
  original save, assert strict parse, no-op SHA, inventory coverage, and
  unchanged-source behavior. Run in-memory edits for every enabled class; do
  not write a game file.
- [x] **Step 8: Commit the original X-Ray writer slice with evidence.** Use:
  `git add editor/xray_container.py editor/xray_save.py editor/models.py editor/prepare.py save_format.py tests/test_xray_container.py tests/test_xray_save.py tests/test_web_bridge.py tests/test_cli.py docs/evidence/XRAY_INVENTORY_2026-09-15.md && git commit -m "feat: add catalog-backed X-Ray inventory edits"`.

## Task 5: Preserve and normalize S.T.A.L.K.E.R. 2 under the same model

**Files:**

- Modify: `editor/formats.py`, `save_format.py`, `editor/service.py`,
  `ui/inventory_model.py`, `web/web_bridge.py`
- Test: `tests/test_formats.py`, `tests/test_save_format.py`,
  `tests/test_web_bridge.py`, `tests/test_ui_inventory.py`

- [x] **Step 1: Write failing compatibility tests** requiring the S2 adapter to
  expose the same release metadata/capability JSON as X-Ray profiles while
  preserving existing money, stack, CRC, Kraken, backup, and raw-round-trip
  behavior.
- [x] **Step 2: Run the compatibility tests and confirm the missing common
  metadata/capability output.**
- [x] **Step 3: Implement the adapter metadata and capability projection.** Do
  not rewrite the established S2 parser or loosen its wallet-anchor guards.
- [x] **Step 4: Run the complete existing S2 regression and web bridge tests.**
- [x] **Step 5: Commit the normalization separately from X-Ray changes.** Use:
  `git add editor/formats.py save_format.py editor/service.py ui/inventory_model.py web/web_bridge.py tests/test_formats.py tests/test_save_format.py tests/test_web_bridge.py tests/test_ui_inventory.py && git commit -m "refactor: expose shared S.T.A.L.K.E.R. 2 capabilities"`.

## Task 6: Obtain and characterize official Enhanced Edition saves

**Files:**

- Create: `tests/fixtures/ee/README.md` containing only hashes, sizes,
  version labels, and provenance; no private save bytes.
- Create: `editor/ee_profiles.py` only after a real format is identified.
- Modify: `editor/formats.py`, `editor/platforms.py`,
  `docs/evidence/EE_FORMATS_2026-09-15.md`
- Test: `tests/test_ee_profiles.py`, `tests/test_formats.py`

- [x] **Step 1: Inventory local official EE manifests, save directories, and
  candidate extensions again without printing private filenames.**
- [x] **Step 2: Search public sources for legally usable official EE sample
  saves or reproducible format descriptions.** Keep URLs, hashes, sizes, and
  licenses in the evidence document; do not place downloaded personal saves in
  Git.
- [ ] **Step 3: Write failing format-probe tests for each available EE sample.**
  Assert exact header/container, compression, version, game identity, and
  wrong-game rejection before exposing any inventory field.
- [ ] **Step 4: Implement one EE adapter per proven container.** Reuse X-Ray
  code only when the bytes and versioned serialization prove compatibility;
  otherwise create a separate parser. Add `.scs`/sidecar handling only where
  the actual save format requires it.
- [x] **Step 5: Keep an unavailable profile visible but disabled when no sample
  exists.** The UI must say which official release lacks evidence instead of
  claiming support from the original parser.
- [ ] **Step 6: Commit each accepted EE profile with its evidence row.** Use a
  separate commit such as `git add editor/ee_profiles.py editor/formats.py
  tests/test_ee_profiles.py tests/fixtures/ee/README.md
  docs/evidence/EE_FORMATS_2026-09-15.md && git commit -m "feat: support verified official EE profile"`;
  do not mark all three Enhanced Editions accepted from one game's sample.

## Task 7: Capability-driven Qt and web UX

**Files:**

- Modify: `ui/main_window.py`, `ui/save_slots_view.py`, `ui/settings_view.py`,
  `ui/inventory_view.py`, `ui/inventory_model.py`, `ui/changes_view.py`,
  `ui/backups_view.py`, `web/index.html`, `web/app.js`, `web/web_bridge.py`
- Test: `tests/test_ui_inventory.py`, `tests/test_ui_theme.py`,
  `tests/test_save_slots.py`, `tests/test_settings.py`,
  `tests/test_web_bridge.py`

- [x] **Step 1: Write failing UI/bridge tests** for release selection,
  capability flags, unsupported candidate display, catalog-resolved names,
  explicit unknown values, disabled unsupported actions, and extension-preserving
  download names.
- [x] **Step 2: Run the tests and verify the UI currently has format-specific
  controls/labels rather than capability-driven controls.**
- [x] **Step 3: Implement the shared snapshot JSON.** Include release/edition,
  capabilities, catalog status, warnings, and per-row editability; keep money,
  inventory, and metadata values sourced from the parser only.
- [x] **Step 4: Implement the Qt selector and staged forms.** Use the existing
  worker for discovery and prepare/export paths. Disable unsupported controls
  before any worker starts and show the exact parser reason.
- [x] **Step 5: Implement the web selector, local file input, drag/drop, and
  download.** Do not add a server endpoint, browser folder scan, or a second
  parser. Regenerate `web/pysrc.json` from sources.
- [x] **Step 6: Run offscreen Qt tests, web bridge tests, `node --check web/app.js`,
  and generated-artifact checks.**
- [x] **Step 7: Commit the common UX slice.** Commit `1c9cd80` gates the
  shared Qt/web capability controls and bridge.
  `git add ui/main_window.py ui/save_slots_view.py ui/settings_view.py ui/inventory_view.py ui/inventory_model.py ui/changes_view.py ui/backups_view.py web/index.html web/app.js web/web_bridge.py tests/test_ui_inventory.py tests/test_ui_theme.py tests/test_save_slots.py tests/test_settings.py tests/test_web_bridge.py web/pysrc.json && git commit -m "feat: expose shared release capabilities in Qt and web"`.

## Task 8: Evidence, packaging, deployment, and final acceptance

**Files:**

- Modify: `README.md`, `docs/STATUS.md`, `docs/tasks/tasks.json`,
  `docs/tasks/INDEX.md`, `docs/evidence/*.md`, `web/README.md`
- Generate: `web/pysrc.json`, `web/theme.css`
- Test: all existing tests plus release-specific corpus scripts

- [x] **Step 1: Add a deterministic corpus verifier** that reports only
  release IDs, counts, versions, SHA-match counts, edit round-trip counts,
  and failure summaries; it must never print or persist private save bytes.
- [x] **Step 2: Run the verifier for every available original and EE profile.**
  Record separate local-parser, browser-bridge, and game-load/re-save statuses.
- [x] **Step 3: Run the full local gates:**
  `PYTHON=.venv/bin/python make check`,
  `QT_QPA_PLATFORM=offscreen PYTHONPATH=. .venv/bin/python -m pytest tests -q`,
  `node --check web/app.js`, `git diff --check`, and generated artifact checks.
- [ ] **Step 4: Build the web artifact with `make web` and serve it locally with
  `make web-serve`; exercise file open, inspect, preview, and download for each
  browser-accepted profile without uploading a save.
- [x] **Step 5: Run the packaging plan/build on the available host.** Record
  Linux package status separately from Windows package/GUI status; do not call
  a Windows runtime gate green from Linux output.
- [x] **Step 6: Deploy only after the artifact guards pass.** Run the existing
  web deployment command if credentials and the configured project are
  available; record the deployment URL, revision, and read-back status. Never
  put saves or private catalogs in `web/`.
- [x] **Step 7: Update docs and task statuses with exact evidence, commit/PR,
  deployment, and open gates.** A local green suite cannot close missing EE or
  in-game acceptance rows.
- [ ] **Step 8: Review the final diff, current branch, remote state, generated
  files, and clean working tree.** Only then report completion or the exact
  remaining external gate.

## Plan Completion Criteria

The plan is complete only when the acceptance matrix has a row for every
official release/build claimed by the UI, each enabled mutation has strict
round-trip and matching-game evidence, desktop discovery/manual selection and
web local-file flows are tested, the deployment read-back is recorded, and the
final report distinguishes local, browser, platform, cloud, and game-runtime
evidence. If an Enhanced Edition cannot be characterized because no real
official save is available, that profile remains explicitly disabled and the
overall goal is not described as 100% complete.
