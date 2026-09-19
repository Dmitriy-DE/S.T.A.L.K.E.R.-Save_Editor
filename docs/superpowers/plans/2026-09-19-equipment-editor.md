# Equipment Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the release-aware Equipment Editor described in `docs/specs/EQUIPMENT_EDITOR.md`, with safe durability staging and bulk repair for proven X-Ray items and explicit research/read-only boundaries for S.T.A.L.K.E.R. 2 and Enhanced Editions.

**Architecture:** Add one immutable equipment projection layer over `InventoryItem`, and attach release-scoped maturity metadata to the existing `FormatCapabilities`. Both Qt and web will render that projection. Staging remains an immutable `EditPlan`; format writers remain the final authority and refuse unsupported or ambiguous anchors.

**Tech Stack:** Python 3.11+, dataclasses, PySide6, the existing `EditorService`/`EditPlan` pipeline, static JavaScript web shell, pytest/pytest-qt, ruff, mypy.

**Spec:** `docs/specs/EQUIPMENT_EDITOR.md`

## Global Constraints

- Keep seven profiles independent; Original and Enhanced Edition adapters never share a writer without release-specific evidence.
- Separate user category (`weapon`, `armor`, `helmet`, `other`) from serializer family (`weapon`, `outfit`, and other format-specific values).
- Preserve source SHA, immutable preview, exclusive backup, CRC/round-trip, and read-back guards.
- Never promote an S2 scalar candidate into a production writer without controlled samples and game load/re-save evidence.
- Unknown, missing, or ambiguous fields remain read-only with an explicit reason.
- Qt and web use the same core projection and capability metadata; no second parser or writer is introduced.
- Do not write personal saves, credentials, or cloud state into Git.

## Review Focus

- A CoP helmet must display as `helmet` while retaining serializer family `outfit`; test in Task 2.
- A damaged but ambiguous/missing condition anchor must be skipped rather than staged; test in Task 3.
- Bulk repair must not include ammo, quest items, unknown categories, or read-only S2 rows; test in Task 3.
- S2 and each EE profile must expose a concrete maturity/reason instead of inheriting original-X-Ray support; test in Task 1 and Task 4.
- Qt and web must serialize the same rows and maturity fields without fabricated names/icons; test in Task 5.

### Task 1: Shared capability maturity and equipment projection

**Files:**
- Create: `editor/equipment.py`
- Modify: `editor/capabilities.py`
- Modify: `editor/formats.py`
- Modify: `save_format.py`
- Test: `tests/test_equipment.py`
- Test: `tests/test_capabilities.py`
- Test: `tests/test_formats.py`

**Interfaces:**
- Consumes: immutable `InventoryItem`, `ItemCatalog`, `ReleaseDescriptor`, and existing format capability booleans.
- Produces: `EquipmentCategory`, `EquipmentLocation`, `SupportMaturity`, `FeatureSupport`, `EquipmentSupport`, `EquipmentItem`, `equipment_items()`, and `equipment_support_for_release()`.

- [ ] **Step 1: Write failing projection and maturity tests.** Assert that an exact X-Ray weapon maps to category `weapon`, an `outfit` maps to `armor`, a `helm_` catalog key maps to `helmet` only for the CoP/known helmet case, storage maps to equipped/inventory/unknown, and S2/EE support has explicit maturity and reason fields.
- [ ] **Step 2: Run `pytest tests/test_equipment.py tests/test_capabilities.py tests/test_formats.py -q`; confirm failure because the projection and metadata types do not exist.**
- [ ] **Step 3: Implement immutable enums/dataclasses and exact classification.** Preserve the original `InventoryItem.category` and `serialization_family`; derive display taxonomy only from release-scoped catalog metadata and conservative key/slot evidence. Add `equipment` metadata to `FormatCapabilities.as_dict()` while keeping all existing boolean fields stable.
- [ ] **Step 4: Run the targeted tests and then `pytest tests/test_capabilities.py tests/test_formats.py -q`; confirm green.**
- [ ] **Step 5: Commit `feat: add release-aware equipment projection`.**

### Task 2: X-Ray equipment taxonomy and item metadata

**Files:**
- Modify: `editor/equipment.py`
- Modify: `editor/xray_catalog.py`
- Modify: `editor/xray_save.py`
- Modify: `save_format.py`
- Test: `tests/test_equipment.py`
- Test: `tests/test_xray_durability.py`
- Test: `tests/test_xray_catalog.py`

**Interfaces:**
- Consumes: Task 1 projection and the existing X-Ray condition/placement anchors.
- Produces: catalog-aware equipment rows with display category, serializer family, exact location, current condition, and per-item mutation reasons.

- [ ] **Step 1: Add failing tests for weapon, armor, CoP helmet, equipped item, backpack item, and unknown condition rows using the existing X-Ray fixtures.** Include assertions that a helmet remains serializer family `outfit` and that no category is inferred from an unverified generic name.
- [ ] **Step 2: Run the targeted tests and observe the expected taxonomy/metadata failures.**
- [ ] **Step 3: Implement the catalog bridge.** Add only exact release-scoped mappings; preserve unknown names and icons as unknown; expose the existing condition codec result without changing offsets or the writer.
- [ ] **Step 4: Run `pytest tests/test_equipment.py tests/test_xray_durability.py tests/test_xray_catalog.py -q`.**
- [ ] **Step 5: Commit `feat: classify xray equipment safely`.**

### Task 3: Durable staging and bulk repair

**Files:**
- Create: `editor/equipment_edits.py`
- Create: `ui/equipment_model.py`
- Create: `ui/equipment_view.py`
- Modify: `ui/main_window.py`
- Modify: `ui/inventory_view.py`
- Test: `tests/test_equipment_edits.py`
- Test: `tests/test_ui_equipment.py`

**Interfaces:**
- Consumes: `EquipmentItem`, `EquipmentSupport`, existing `EditPlan.durability`, and `LocalSnapshot`.
- Produces: `RepairSkip`, `RepairStageResult`, `stage_repair()`, and `stage_bulk_repair()`; Qt actions for individual and bulk repair.

- [ ] **Step 1: Write failing pure tests for 0%, 50%, 100%, invalid values, no-op reset, missing/ambiguous anchors, and bulk filters.** Verify only writable equipment produces durability tuples and skipped rows include a stable reason.
- [ ] **Step 2: Run `pytest tests/test_equipment_edits.py -q`; confirm the expected missing-interface failures.**
- [ ] **Step 3: Implement finite 0…1 validation and deterministic handle-deduplicated staging.** Do not mutate `SaveInfo` or source bytes. Keep the existing writer preflight as the final guard.
- [ ] **Step 4: Add `EquipmentTableModel` and `EquipmentView` with product filters, individual reset, bulk filter buttons, catalog icons, and maturity reasons.** Use Russian product terminology; keep technical codec terms in tooltips. Wire staged values into existing preview/apply counters and clear actions without replacing the established inventory surface.
- [ ] **Step 5: Run `pytest tests/test_equipment_edits.py tests/test_ui_equipment.py tests/test_edit_plan.py tests/test_ui_inventory.py -q`.**
- [ ] **Step 6: Commit `feat: add safe individual and bulk equipment repair staging`.**

### Task 4: S2 research boundary and independent Enhanced Edition profiles

**Files:**
- Create: `editor/equipment_research.py`
- Create: `tools/research_equipment.py`
- Modify: `editor/formats.py`
- Modify: `editor/releases.py`
- Modify: `README.md`
- Modify: `docs/STATUS.md`
- Create: `docs/evidence/EQUIPMENT_EDITOR_2026-09-19.md`
- Test: `tests/test_equipment_research.py`
- Test: `tests/test_releases.py`
- Test: `tests/test_formats.py`

**Interfaces:**
- Consumes: shared projection, parsed save-local S2 names, and explicit sample paths.
- Produces: read-only research report with source hashes, release id, observed categories, and exact blockers; seven release-specific support descriptors.

- [ ] **Step 1: Write failing tests for a multi-sample report and for S2/EE capabilities.** Assert that no writer capability is enabled from a scalar observation alone and that EE never falls through to an original adapter.
- [ ] **Step 2: Run the targeted tests and observe the expected missing-report/profile failures.**
- [ ] **Step 3: Implement the research report.** It reads only explicit files, records SHA-256 and parser observations, reports missing controlled A/B/game evidence, and never writes a save. Add independent EE metadata with `unsupported` reasons.
- [ ] **Step 4: Add CLI argument validation and human-readable JSON/text output; test malformed paths and mixed release samples.**
- [ ] **Step 5: Run `pytest tests/test_equipment_research.py tests/test_releases.py tests/test_formats.py -q`.**
- [ ] **Step 6: Commit `feat: document s2 and enhanced equipment evidence gates`.**

### Task 5: Shared web bridge and Equipment view

**Files:**
- Modify: `web/web_bridge.py`
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/style.css`
- Modify: `ui/inventory_model.py`
- Modify: `ui/inventory_view.py`
- Test: `tests/test_web_bridge.py`
- Test: `tests/test_web_equipment.py`
- Test: `tests/test_ui_equipment.py`

**Interfaces:**
- Consumes: Task 1 projection, Task 3 staging result, and existing web `prepare()` contract.
- Produces: JSON equipment rows/support metadata and matching Qt/web filters, controls, staged before→after display, and skipped-item messages.

- [ ] **Step 1: Write failing bridge tests for equipment rows, maturity metadata, filters, and repair staging parity with desktop.**
- [ ] **Step 2: Run targeted web/Qt tests and confirm missing JSON/UI behavior.**
- [ ] **Step 3: Add a bridge serializer that emits only projection values and exact catalog icon metadata; leave S2/EE condition fields read-only when unsupported.**
- [ ] **Step 4: Add web controls and Qt equipment presentation using the same filter names and support reasons.**
- [ ] **Step 5: Run `pytest tests/test_web_bridge.py tests/test_web_equipment.py tests/test_ui_equipment.py -q`, `node --check web/app.js`, and `make PYTHON=/home/dmytro/Projects/save-editor/.venv/bin/python web`.**
- [ ] **Step 6: Commit `feat: expose shared equipment editor in qt and web`.**

### Task 6: Full gates, generated assets, and release documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/specs/CROSS_PLATFORM_EDITOR.md`
- Modify: `web/pysrc.json`
- Modify: `web/theme.css`
- Test: `tests/test_docs_consistency.py`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Consumes: all prior shared interfaces and committed evidence limits.
- Produces: current documentation that distinguishes implemented X-Ray repair from S2/EE research/read-only support and reproducible generated web artifacts.

- [ ] **Step 1: Add failing consistency assertions for Equipment terminology, release maturity, and generated web parity.**
- [ ] **Step 2: Run the targeted documentation tests and observe stale-document failures.**
- [ ] **Step 3: Update docs and regenerate only repository-approved web artifacts.** Document that structural round-trip is not game acceptance and list the exact S2 evidence still required for a writer.
- [ ] **Step 4: Run `make PYTHON=/home/dmytro/Projects/save-editor/.venv/bin/python check`, `make PYTHON=/home/dmytro/Projects/save-editor/.venv/bin/python test`, `node --check web/app.js`, and `git diff --check`.**
- [ ] **Step 5: Commit `docs: record equipment editor scope and evidence gates`.**

## Self-review

- Spec coverage: Tasks 1–3 cover the shared model, X-Ray taxonomy, repair controls, immutable staging, and all requested filter/action cases. Task 4 covers seven release gates and the reproducible S2 research path. Task 5 covers Qt/web parity. Task 6 covers documentation and generated bundle gates.
- No production writer is opened for S2 or Enhanced Editions; this is deliberate and required by the evidence boundary.
- Existing booleans and EditPlan shapes remain backwards-compatible; new metadata is additive.
- Review focus cases are pinned to concrete tests in Tasks 1–5.
