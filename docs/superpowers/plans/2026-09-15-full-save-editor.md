# Full STALKER Save Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and expose a complete editor for the four official STALKER game families, including inventory, durability, faction data, faction membership, backups, and explicit desktop writes, while keeping unsupported releases and mods visibly read-only.

**Architecture:** Keep parsing, validation, catalogs, risk classification, and storage in the shared `editor/` core. Qt, CLI, and the static browser editor consume the same snapshot and edit-plan contracts; the browser only reads a local file and downloads a result. Each M-card is an isolated branch and PR, and a capability is enabled per official release only after its edited save loads and is re-saved by that game.

**Tech Stack:** Python 3.11/3.12, standard-library parser/storage core, PySide6 desktop UI, pytest/pytest-qt, mypy, ruff, Pyodide/static JavaScript web bridge, official X-Ray/OpenXRay source evidence, GitHub Actions Linux/Windows matrix.

**Spec:** `docs/plans/FULL_EDITOR.md`, `docs/tasks/M10.md`–`docs/tasks/M16.md`, and the official-release descriptors in `editor/releases.py`.

## Global Constraints

- Official releases only: S.T.A.L.K.E.R. 2, Shadow of Chornobyl, Clear Sky, and Call of Pripyat; original and Enhanced Edition descriptors remain separate profiles and are never silently interchanged.
- Mods are out of scope. Resource catalogs must come from the selected official installation; no item, faction, SID, or quest list is hard-coded in Python or JavaScript.
- M10 is the first feature gate. Until evidence exists for a release, its mutation capability remains false even when structural round-trip tests pass.
- A field is confirmed only by source evidence plus independent save pairs plus the required in-game load/re-save/read-back result; a type key is not a SID, a guessed record end is not a registry boundary, and an orphan is not automatically garbage.
- Personal saves, screenshots, credentials, and full private handoffs never enter Git. Evidence stores hashes, versions, and results only.
- Preserve source-SHA, backup, CRC/container, no-op round-trip, persistence/read-back, and unknown-field guards. Never perform automatic Steam writes or launch a game.
- Desktop in-place replacement is explicit and requires a verified backup; default export remains a new copy. The browser never writes to a game directory.
- Each card uses one branch and one PR, runs `PYTHON=.venv/bin/python make check` and `PYTHON=.venv/bin/python make test`, records exit codes and limitations, then merges only after all four CI jobs pass.

---

## File Map

- Modify `editor/capabilities.py` and `editor/formats.py` to represent per-release gameplay evidence and risk-gated mutation capabilities.
- Modify `editor/models.py`, `save_format.py`, and `editor/service.py` for immutable durability/faction edit plans, snapshots, warnings, and shared front-end parity.
- Modify `editor/catalog.py` and `editor/xray_catalog.py`; add `editor/xray_factions.py` when faction parsing would otherwise enlarge the item-resource reader beyond one responsibility. These files own resource-derived item, faction, localization, and serializer metadata.
- Modify `editor/xray_save.py`; add `editor/xray_item_state.py` for source-backed condition/relationship/player-community codecs so format-specific reads remain isolated from UI code.
- Modify `editor/storage.py` for explicit same-path game replacement and verified in-place restore; retain the existing safe new-copy export.
- Modify `ui/main_window.py`, `ui/inventory_view.py`, `ui/changes_view.py`, and `ui/backups_view.py` for item condition, faction controls, risk warnings, explicit game-folder writes, and restore.
- Modify `web/web_bridge.py`, `web/app.js`, `web/catalogs.json`, and `tools/build_web_catalogs.py` so browser snapshots expose exactly the same supported data and clearly omit direct game-folder writes.
- Add `tools/prepare_ingame_verification.py` and `tools/verify_ingame_result.py`; add one focused test module per card under `tests/` and one evidence document per source/gameplay gate under `docs/evidence/`.
- Update `docs/tasks/tasks.json`, generated `docs/tasks/INDEX.md`, `docs/STATUS.md`, and the relevant task/evidence documents only when the corresponding card's evidence actually changes.

## Completed Baseline

- [x] PR #53 was retitled and described as M01–M09 implementation, merged into `main` as `28dbadf7cc0ef4971eb777bb191496257bd72c4e`, and its four CI jobs passed.
- [x] PRs #48–#52 are merged as ancestors of PR #53 and have explanatory comments; PRs #54–#56 are closed as obsolete with explanatory comments.
- [x] Remote and local `codex/m01`–`codex/m09` branches were deleted; `main` and `gh-pages` remain.

### Task 1: M10 — reproducible in-game verification protocol

**Branch/PR:** `codex/m10-ingame-verification`, one PR for M10.

**Files:**
- Create: `tools/prepare_ingame_verification.py`
- Create: `tools/verify_ingame_result.py`
- Create: `tests/test_ingame_protocol.py`
- Create: `docs/evidence/INGAME_VERIFICATION.md`
- Modify: `editor/capabilities.py`, `editor/formats.py`, `docs/tasks/M10.md`, `docs/tasks/tasks.json`, `docs/tasks/INDEX.md`, `docs/STATUS.md`

**Interfaces:**
- `prepare_ingame_verification.prepare_source_copy(source: Path, release_id: str, workspace: Path, money: int) -> VerificationManifest` copies a user-selected save into a user-selected temporary workspace, prepares exactly one money edit through the registered format, and never writes the source or an installation directory.
- `verify_ingame_result.verify_resaved_save(manifest: Path, resaved: Path) -> VerificationResult` hashes the re-saved file, parses it with the selected release, and reports the observed money, format, container/actor versions, and parser warnings.
- `VerificationManifest` and `VerificationResult` are JSON-serializable frozen dataclasses containing paths only as user-local metadata and containing no save bytes.
- `FormatCapabilities` gains an evidence-backed per-release mutation projection; an unverified release returns `edit_money=False` and all structural mutation fields false.

- [ ] **Step 1: Write failing protocol tests.** Cover source immutability, exactly one changed money value, generated output SHA, wrong-release rejection, malformed re-save rejection, and a manifest that contains hashes/results but no embedded save bytes.

```python
from test_xray_save import _fixture

def test_prepare_protocol_changes_only_money_and_keeps_source(tmp_path):
    source = tmp_path / "source.sav"
    original = _fixture()
    source.write_bytes(original)
    manifest = prepare_source_copy(source, "stalker-cop", tmp_path / "run", 900)
    assert source.read_bytes() == original
    assert manifest.source_sha256 != manifest.edited_sha256
    assert manifest.edited_money == 900
```

- [ ] **Step 2: Run the focused tests and record the expected failure.**

Run: `.venv/bin/python -m pytest tests/test_ingame_protocol.py -q`

Expected: FAIL because the protocol dataclasses and commands do not exist yet.

- [ ] **Step 3: Implement the safe preparation and read-back commands.** Use the existing `detect_or_raise`, `prepare_xray`/`prepare_edit`, `SourceRef`, SHA-256, and `EditorService`; write all artifacts below a caller-provided workspace such as `/tmp/stalker-save-editor-ingame/<release-id>`. Reject source/output equality, existing output, unknown release, and all edits except one money field. Print the exact commands for the owner to launch the game and to provide the re-saved path.

- [ ] **Step 4: Add the evidence document with honest per-release rows.** Include `stalker2`, original SoC/CS/CoP, and separate EE rows. Each row must have game/release, installed version/build, source SHA, edited SHA, resaved SHA, observed value, parser result, visible game result, and status `pending-owner-run`, `passed`, or `failed`; no guessed pass values. The procedure must say: close the game, copy one save, edit only money, load the copy, inspect the value, save in-game, parse the new file, and record the result. State that one release never proves another.

- [ ] **Step 5: Gate capabilities per release.** Keep unverified profiles read-only in `FormatCapabilities`; do not enable a mutation field because a synthetic round-trip or a different game passed. When the owner supplies a row with successful load and re-save, enable only `edit_money` for that exact release and add a regression test for the evidence row. Enhanced profiles remain explicit unsupported/read-only until their own sample is verified.

- [ ] **Step 6: Run the focused tests, full gates, and commit the M10 prep.**

Run: `.venv/bin/python -m pytest tests/test_ingame_protocol.py tests/test_capabilities.py tests/test_formats.py -q`

Run: `PYTHON=.venv/bin/python make check`

Run: `PYTHON=.venv/bin/python make test`

Expected: all commands exit 0; no capability is marked in-game verified by synthetic tests.

- [ ] **Step 7: Push, open the M10 PR, and stop at the owner-only gate.** The exact owner action is to run the generated preparation command for one save per official release, launch each corresponding game manually, load the edited copy, save it again, then run the generated verification command. Do not launch a game or write a real game folder from Codex. Record hashes/results in `docs/evidence/INGAME_VERIFICATION.md` and continue only after the rows are supplied.

### Task 2: M11 — resource-backed item and faction catalogs

**Branch/PR:** `codex/m11-resource-catalogs`, one PR for M11 after M10 evidence is available.

**Files:**
- Modify: `editor/catalog.py`, `editor/xray_catalog.py`, `editor/formats.py`, `editor/service.py`
- Create: `editor/xray_factions.py`, `tests/test_xray_factions.py`, `tests/test_catalog_bundle.py`, `docs/evidence/XRAY_FACTION_CATALOG.md`
- Modify: `tools/build_web_catalogs.py`, `web/catalogs.json`, `web/web_bridge.py`, `ui/inventory_view.py`, `ui/main_window.py`, `tests/test_xray_catalog.py`, `tests/test_web_bridge.py`, `docs/tasks/M11.md`, `docs/tasks/tasks.json`, `docs/tasks/INDEX.md`, `docs/STATUS.md`

**Interfaces:**
- `FactionDefinition(key: str, display_name: str | None, source: str, release_id: str)` is immutable and release-scoped.
- `FactionCatalog(release_id: str, source_root: Path | None, factions: tuple[FactionDefinition, ...])` resolves exact keys and raises an explicit `CatalogLookupError` for a missing key.
- `GameCatalog(release_id: str, items: ItemCatalog, factions: FactionCatalog)` is the shared desktop/web catalog payload; it never combines catalogs with different release IDs.

- [ ] **Step 1: Add failing cross-release catalog tests.** Build temporary LTX/localization trees for SoC, CS, and CoP with distinct faction sections and assert that each catalog contains only its own resource-derived keys, missing installations return a visible unavailable result, and the web JSON matches the desktop payload.
- [ ] **Step 2: Run focused tests and verify they fail.**

Run: `.venv/bin/python -m pytest tests/test_xray_factions.py tests/test_catalog_bundle.py -q`

Expected: FAIL because faction definitions and the combined catalog do not exist.

- [ ] **Step 3: Implement resource extraction.** Reuse the existing archive/LTX/localization reader; discover faction/community sections from resource inheritance and serialized references, preserve the exact source path, and derive display names only from the selected language resources. Do not add lists of known faction names or numeric IDs.
- [ ] **Step 4: Connect the release-scoped catalog to all front ends.** Extend `FormatInspection`/service payloads without changing CLI compatibility; make item/faction selections disappear with a clear “official resource catalog unavailable” reason when no install is found; generate browser metadata without shipping game archives or local paths.
- [ ] **Step 5: Run focused and full gates, inspect generated JSON, update evidence, commit, push, open, and merge M11.** Confirm the intersection of the three original item catalogs is 261 only as observed evidence, not as a hard-coded contract; record actual counts and source hashes for the resource metadata.

### Task 3: M12 — source-backed durability for equipped and inventory items

**Branch/PR:** `codex/m12-durability`, one PR for M12 after M10 and M11.

**Files:**
- Create: `editor/xray_item_state.py`, `tests/test_xray_durability.py`, `docs/evidence/XRAY_ITEM_SERIALIZATION.md`
- Modify: `editor/models.py`, `editor/catalog.py`, `editor/xray_save.py`, `editor/formats.py`, `editor/capabilities.py`, `ui/inventory_model.py`, `ui/inventory_view.py`, `ui/changes_view.py`, `web/web_bridge.py`, `web/app.js`, `tests/test_xray_save.py`, `tests/test_ui_inventory.py`, `tests/test_web_bridge.py`, `docs/tasks/M12.md`, `docs/tasks/tasks.json`, `docs/tasks/INDEX.md`, `docs/STATUS.md`

**Interfaces:**
- `EditPlan.durability: tuple[tuple[int, float], ...]` stores canonical condition in the closed interval `[0.0, 1.0]` keyed by object handle.
- `InventoryItem.condition: float | None` and `InventoryItem.storage: Literal["equipped", "inventory"] | None` expose read-only unknowns honestly.
- `XRayItemStateCodec.read_condition(raw: bytes, obj: XRayObject, family: str) -> float` and `.patch_condition(raw: bytes, obj: XRayObject, family: str, value: float) -> bytes` are selected by release/serializer family, never by a guessed byte offset.

- [ ] **Step 1: Record source evidence before coding.** Read and cite the relevant inventory object save/load order from `ixray-1.0-stsoc`, `ixray-1.5-stcs`, `ixray-1.6-stcop`, and OpenXRay `xray-16`; record the field order and differences for spawn 118/124/128 in `docs/evidence/XRAY_ITEM_SERIALIZATION.md`.
- [ ] **Step 2: Add failing synthetic and corpus tests.** Cover one equipped and one actor-inventory weapon/armor object per original release, at least three independent save pairs, range rejection, unknown-family read-only behavior, and no-op byte-preserving round-trip.
- [ ] **Step 3: Implement format-specific condition codecs.** Parse the field only when the complete source-backed serializer window matches; reject NaN, infinity, and values outside `[0, 1]`; retain the original bytes for unknown objects. Do not infer durability from nearby floats.
- [ ] **Step 4: Expose staged repair in Qt and browser download flows.** Show “equipped” versus “inventory”, before/after condition, and the exact reason for read-only entries. The web may prepare/download an edited copy but must not write to the game directory.
- [ ] **Step 5: Run the focused tests, full gates, M10 read-back checks for each release, update capabilities only for releases that passed, commit, push, open, and merge M12.** A structurally successful patch without in-game confirmation remains read-only.

### Task 4: M13 — catalog-backed add/remove/stack edits with risk warnings

**Branch/PR:** `codex/m13-inventory-edits`, one PR for M13 after M10 and M11.

**Files:**
- Modify: `editor/models.py`, `editor/catalog.py`, `editor/xray_save.py`, `editor/formats.py`, `editor/service.py`, `ui/inventory_view.py`, `ui/changes_view.py`, `ui/main_window.py`, `web/web_bridge.py`, `web/app.js`
- Create: `editor/risk.py`, `tests/test_xray_inventory_edits.py`, `tests/test_risk_warnings.py`, `docs/evidence/XRAY_INVENTORY_EDITS.md`
- Modify: `tests/test_xray_save.py`, `tests/test_service_parity.py`, `tests/test_ui_inventory.py`, `tests/test_web_bridge.py`, `docs/tasks/M13.md`, `docs/tasks/tasks.json`, `docs/tasks/INDEX.md`, `docs/STATUS.md`

**Interfaces:**
- `EditPlan` retains exact `adds`, `detach`, and `stacks` entries and gains no UI-only mutation state; all requests are validated against the selected `GameCatalog` before serialization.
- `classify_item_risk(definition: ItemDefinition) -> RiskLevel` returns `safe`, `world`, or `dangerous`, with `unknown` remaining read-only.
- `XRaySave` validates ammo STATE and UPDATE counts together, exact release catalog membership, serializer-family template compatibility, and actor ownership before add/remove.

- [ ] **Step 1: Add failing tests for ammo dual-state edits, catalog membership, quest-item warning, weight/capacity limits, actor-owned removal, and byte-preserving no-op.** Include a foreign-game key and an unknown serializer family that must be rejected.
- [ ] **Step 2: Implement validation before any length-changing operation.** Reparse after each registry append/remove, allocate a fresh handle, preserve all unrelated chunks, and verify added/deleted inventory through a strict post-build parse. Do not treat a matching type key as proof of a SID or quest safety.
- [ ] **Step 3: Add risk-aware UI changes.** Safe money/count/condition edits are ordinary; world-affecting edits are marked in the change list; quest/unknown-risk deletion requires a concrete warning naming the item and game and a verified backup before direct write. Downloading a copy can still be offered with the warning visible.
- [ ] **Step 4: Run focused/full tests and repeat M10 in-game add/remove/count checks per release.** Enable only the capabilities with a passing row; record negative results as explicit disabled capabilities and reasons.
- [ ] **Step 5: Commit, push, open, and merge M13 after all four CI jobs pass.** Update generated catalogs/evidence and remove no existing backup or round-trip guard.

### Task 5: M14 — faction relations from per-game X-Ray registries

**Branch/PR:** `codex/m14-faction-relations`, one PR for M14 after M10 and M11.

**Files:**
- Create: `editor/xray_factions.py` relation codecs if not created in M11, `tests/test_xray_relations.py`, `docs/evidence/XRAY_FACTION_RELATIONS.md`
- Modify: `editor/models.py`, `editor/xray_save.py`, `editor/formats.py`, `editor/capabilities.py`, `ui/main_window.py`, `ui/changes_view.py`, `web/web_bridge.py`, `web/app.js`, `tests/test_service_parity.py`, `tests/test_web_bridge.py`, `docs/tasks/M14.md`, `docs/tasks/tasks.json`, `docs/tasks/INDEX.md`, `docs/STATUS.md`

**Interfaces:**
- `FactionRelation(source: str, target: str, value: int, threshold: int | None, release_id: str)` is immutable and release-scoped.
- `XRayRelationCodec.read(parsed: XRaySave, catalog: FactionCatalog) -> tuple[FactionRelation, ...]` and `.patch(parsed: XRaySave, edits: tuple[tuple[str, str, int], ...]) -> bytes` preserve unrelated registry entries.
- `EditPlan.relations: tuple[tuple[str, str, int], ...]` is validated for exact catalog membership and release ID before write.

- [ ] **Step 1: Read the community/actor relation serializers and thresholds from the three ixray/OpenXRay source families.** Record Clear Sky warfare-specific structures separately; do not copy a CoP table into CS.
- [ ] **Step 2: Add failing tests for reading three-game relation fixtures, changing one relation only, rejecting a foreign faction, and preserving all unrelated values.** Include bounds and threshold reporting.
- [ ] **Step 3: Implement per-release codecs and shared snapshot serialization.** Unknown relation blocks remain visible/read-only; no guessed offset or zero-filled default is written.
- [ ] **Step 4: Add risk-level `world` UI and browser download presentation.** Show the exact source/target faction names, old/new values, and source-specific threshold if proven.
- [ ] **Step 5: Run full gates and M10 in-game relation checks; enable only proven release capabilities, record failures explicitly, commit, push, open, and merge M14.**

### Task 6: M15 — player faction/community with explicit dangerous warnings

**Branch/PR:** `codex/m15-player-faction`, one PR for M15 after M14.

**Files:**
- Create: `tests/test_player_faction.py`, `docs/evidence/XRAY_PLAYER_FACTION.md`
- Modify: `editor/models.py`, `editor/xray_save.py`, `editor/xray_factions.py`, `editor/service.py`, `editor/capabilities.py`, `ui/main_window.py`, `ui/changes_view.py`, `ui/backups_view.py`, `web/web_bridge.py`, `web/app.js`, `tests/test_service_parity.py`, `tests/test_ui_apply.py`, `docs/tasks/M15.md`, `docs/tasks/tasks.json`, `docs/tasks/INDEX.md`, `docs/STATUS.md`

**Interfaces:**
- `SaveInfo.player_faction: str | None` and `EditPlan.player_faction: str | None` use exact resource-derived faction keys.
- `PlayerFactionWarning(release_id: str, faction_key: str, message: str, source: str)` is shown before a dangerous change; warnings do not silently block a valid explicit edit.
- `EditorService.prepare_dangerous(...)` requires a verified backup receipt for a direct game write and returns the warning/change metadata with the prepared bytes.

- [ ] **Step 1: Record source/script evidence for actor community storage, valid values, and known story rewrites per game.** Include the Clear Sky “quest can overwrite membership” case only when the source or controlled game result supports the exact wording.
- [ ] **Step 2: Add failing tests for reading current membership, exact catalog validation, warning display, foreign-key rejection, and refusal to direct-write without a verified backup.** Test that export-to-new-copy still preserves the warning rather than silently dropping the edit.
- [ ] **Step 3: Implement per-release player-community codecs and danger metadata.** Allow the edit, warn with game-specific text, and keep unknown story constraints as “not known” rather than inventing a block.
- [ ] **Step 4: Add Qt/web parity.** Desktop marks the change dangerous and requires backup before in-place write; web can stage/download with the warning and explicitly states that it cannot write a game folder.
- [ ] **Step 5: Run full gates and M10 load/re-save checks; record both positive and negative outcomes.** A failed game behavior disables only that release’s capability with a reason; it never transfers a result from another game.
- [ ] **Step 6: Commit, push, open, and merge M15 after four green CI jobs.**

### Task 7: M16 — explicit desktop game-folder replacement and one-step restore

**Branch/PR:** `codex/m16-game-folder-write`, one PR for M16 after M10.

**Files:**
- Modify: `editor/storage.py`, `editor/service.py`, `ui/main_window.py`, `ui/changes_view.py`, `ui/backups_view.py`, `editor/platforms.py`
- Create: `tests/test_game_folder_write.py`, `docs/evidence/GAME_FOLDER_WRITE.md`
- Modify: `tests/test_storage.py`, `tests/test_restore.py`, `tests/test_ui_backups.py`, `tests/test_docs_consistency.py`, `web/app.js`, `docs/tasks/M16.md`, `docs/tasks/tasks.json`, `docs/tasks/INDEX.md`, `docs/STATUS.md`

**Interfaces:**
- `editor.storage.replace_game_save(source_path: Path, prepared: PreparedEdit, backup_dir: Path) -> ExportReceipt` creates and hash-verifies the original backup, writes a neighboring temporary file, atomically replaces the selected slot, reads it back, and marks the journal verified only after the output SHA matches.
- `editor.storage.restore_game_save(record: Path | BackupRecord, output_path: Path) -> RestoreReceipt` performs the same verified temporary replacement for an existing slot; corrupt/missing/mismatched backups are rejected.
- `EditorService.write_game_save(...)` is the explicit desktop-only service method; the browser bridge has no method with this capability.

- [ ] **Step 1: Add failing fault-injection tests.** Cover backup hash mismatch, temp write interruption, replace failure, read-back mismatch, corrupt backup refusal, restore success, and stale source SHA; assert that a failed operation leaves the original slot unchanged and cleans up temporary files.
- [ ] **Step 2: Implement same-path storage as a separate function.** Do not weaken `export_local`’s new-copy/no-overwrite contract. Use an exclusive backup, fsync, a temporary neighbor, atomic `os.replace`, fresh read-back hash, and journal status transitions.
- [ ] **Step 3: Add explicit Qt actions.** The user selects a discovered/manual slot, sees the exact target path and backup hash, confirms “write into game folder”, and can restore one verified backup. Warn when the game process is detected; if process state is unknown, say so without claiming it is closed.
- [ ] **Step 4: Keep browser behavior honest.** Remove/disable any direct-write affordance in `web/`; show “download edited copy” and explain that browser sandboxing prevents game-folder replacement.
- [ ] **Step 5: Run the fake-tree tests, full gates, and one controlled desktop verification per supported release after M10.** Record no real game write in Git; only hashes/results go into evidence.
- [ ] **Step 6: Commit, push, open, and merge M16 after four green CI jobs.**

## Final Full-Editor Audit

- [ ] Run `PYTHON=.venv/bin/python make check` and `PYTHON=.venv/bin/python make test` on the final main commit.
- [ ] Run the release matrix against the official descriptors: the four game families and each available original/Enhanced profile have an explicit `supported`, `read-only`, or `unavailable` status; no Enhanced profile is routed through an original parser.
- [ ] Verify desktop, CLI, and browser snapshots agree on money, stacks, catalog membership, durability, faction relations, player faction, risk labels, and unsupported reasons.
- [ ] Verify no personal save bytes, mod resources, hard-coded item/faction lists, credentials, or automatic game-folder writes entered Git.
- [ ] Report every card ID, branch/PR, exact SHA, commands and exit codes, CI result, evidence rows, unverified releases, and the remaining external game-launch boundary. Do not call the editor fully supported where M10 or the game behavior is still unverified.
