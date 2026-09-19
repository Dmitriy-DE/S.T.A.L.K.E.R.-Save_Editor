# S.T.A.L.K.E.R. 2 Equipment Writer Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make confirmed S.T.A.L.K.E.R. 2 armor durability editable in the real Qt editor, include confirmed equipped records in the inventory view, remove the false 0% state, and preserve explicit read-only gates for unproven weapon/upgrades/add-item serializers.

**Architecture:** Add a small pure S2 equipment-state codec, connect it to the existing save_format inspection and Kraken/CRC transaction, then expose it through the existing immutable EditPlan and Qt staging flow. Do not create a second editor surface or guess a constructor for UE5 objects.

**Tech Stack:** Python 3, pytest, existing Kraken/CRC codec, PySide6 when available, Markdown evidence and superpowers ledger.

**Spec:** docs/superpowers/specs/2026-09-19-s2-equipment-state-design.md

## Global Constraints

- Work only in the isolated codex/s2-equipment-writer worktree; do not merge, push, deploy, or modify main.
- Use apply_patch for source and documentation edits.
- Follow TDD: each implementation change starts with a failing focused test.
- Never write the supplied Steam Cloud files; all corpus checks are read-only.
- Never label structural round trip as game acceptance.
- Keep S2 weapon condition, upgrades writer, and arbitrary item giving disabled until a controlled pair proves each serializer.

## Review Focus

- An unknown condition must never render as numeric 0%.
- The equipped discovery guard must not reclassify synthetic orphans.
- The armor anchor must be exact (same handle, kind=1, +0x23, +4) and must reject malformed/range-invalid data.
- Combined money/stack/durability transactions must rebuild and verify all requested fields.
- EditPlan SHA protection and the existing no-side-effect preview/apply flow must remain intact.
- No capability flag may accidentally enable S2 upgrades or arbitrary add-item construction.

---

## Task 1: Add the exact S2 armor condition codec

**Files:**

- Add editor/s2_item_state.py.
- Add tests/test_s2_item_state.py.

**Interfaces:**

- S2ConditionAnchor as specified by the design document.
- read_s2_armor_condition(...) and patch_s2_armor_condition(...).

**Steps:**

- [ ] Build a private raw-record fixture with a valid top-level handle and the nested same-handle state at record + 0x23.
- [ ] Write failing tests for read, exact four-byte patch, invalid kind, missing nested handle, NaN/out-of-range values, and non-finite requested values.
- [ ] Implement the pure codec with bounds checks and no imports from save_format.
- [ ] Run python3 -m pytest tests/test_s2_item_state.py; expected result: all focused tests pass.

## Task 2: Show equipped S2 records and condition metadata

**Files:**

- Modify save_format.py.
- Add focused cases to tests/test_s2_item_state.py or add tests/test_s2_equipment_inventory.py.

**Interfaces:**

- _inventory_details may emit an equipped InventoryItem with empty cells and unknown grid coordinates.
- locate_orphans must exclude only records passing the narrow equipped-shape predicate.

**Steps:**

- [ ] Add failing tests proving a kind-1 equipped fixture is listed with position_label="экипировано", condition_editable=True, and its decoded value.
- [ ] Add a regression test proving the existing kind-0 synthetic orphan remains an orphan when it lacks the S2 nested shape.
- [ ] Connect the codec and add a small shape predicate for owned non-grid S2 equipment.
- [ ] Keep grid item ordering and existing unknown-kind behavior unchanged.
- [ ] Run the focused S2 tests plus python3 -m pytest tests/test_save_baseline.py tests/test_parser_coverage.py; expected result: all selected tests pass.

## Task 3: Add the S2 durability transaction and capability

**Files:**

- Modify save_format.py.
- Modify editor/prepare.py.
- Modify editor/formats.py.
- Add tests/test_s2_durability.py.

**Interfaces:**

- patch_save(..., durability: dict[int, float] | None = None).
- prepare_edit passes the frozen EditPlan.durability mapping.
- S2 capabilities enable only experimental edit_durability in addition to the existing experimental money edit.

**Steps:**

- [ ] Write failing tests for S2 prepare_edit durability round trip, exact changed bytes, combined money+durability, stale SHA rejection, and non-armor rejection.
- [ ] Implement the raw patch and post-rebuild verification without changing the public behavior of money/stack/structural operations.
- [ ] Keep plan.adds, S2 upgrades, and unsupported weapon condition rejected with explicit messages.
- [ ] Add a capability regression asserting S2 durability is enabled/experimental while add_items and edit_upgrades remain false.
- [ ] Run python3 -m pytest tests/test_s2_item_state.py tests/test_s2_durability.py tests/test_capabilities.py tests/test_service_parity.py; expected result: all selected tests pass.

## Task 4: Remove the false 0% UI and expose experimental armor editing

**Files:**

- Modify ui/inventory_view.py.
- Add focused assertions to tests/test_ui_inventory.py or add tests/test_ui_s2_durability.py.

**Interfaces:**

- Add an explicit unknown-condition label in the existing condition form.
- Keep the spin box for actual known values; hide it when the value is unknown instead of showing 0.0.

**Steps:**

- [ ] Write a failing Qt test (skipped cleanly when PySide6/pytest-qt is unavailable) for an unknown condition showing an em dash and no active staging controls.
- [ ] Write a failing Qt test for a known S2 armor condition showing the percentage and enabled staging button when capabilities allow it.
- [ ] Implement the visibility/status split while preserving existing X-Ray behavior.
- [ ] Run the focused Qt tests when the Qt test dependency is installed; otherwise run the non-Qt suite and record the environment limitation.

## Task 5: Add evidence and the controlled-pair handoff for remaining writers

**Files:**

- Add docs/evidence/S2_EQUIPMENT_WRITER_2026-09-19.md.
- Modify docs/STATUS.md only where the new boundary/evidence is recorded.

**Interfaces:**

- Documentation must distinguish: armor condition writer implemented experimentally; weapon condition/upgrades/add-item still blocked.
- Include the exact user-controlled protocol for one known armor edit, one known upgrade install, and one known catalog item pickup/give.

**Steps:**

- [ ] Add the corpus result and exact S2 anchor evidence without including private save bytes or paths beyond the already documented local layout.
- [ ] Document how to produce before/after game saves and what byte-level invariants must match before enabling each future capability.
- [ ] Add a regression/documentation check if the repository has one for status/evidence consistency.

## Task 6: Full verification and final review

**Files:**

- No new source files beyond the tasks above.

**Steps:**

- [ ] Run focused tests and then python3 -m pytest tests -k 'not qt_condition_editor_stages_percentage_without_mutating_snapshot' in the current environment.
- [ ] Run make check and fix only regressions caused by this work.
- [ ] Run a read-only corpus inspection against the local S2 cloud directory and confirm no .sav timestamp or contents changed.
- [ ] Perform a fresh self-review of the whole diff against the spec and Review Focus.
- [ ] Report exact branch, commit(s), tests, and the remaining in-game acceptance boundary; do not claim merge/deploy.
