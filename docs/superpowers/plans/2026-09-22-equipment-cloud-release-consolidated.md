# Equipment, Cloud, and Release Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Собрать в один проверяемый поток поддержку оборудования для всех зарегистрированных игр, безопасное исследование и последующее редактирование прочности оружия/брони, read-only разбор модулей и устройств S.T.A.L.K.E.R. 2, единый UI, корректный Steam Cloud/repack, а также полный quality/release gate с отдельными installer и portable артефактами для Windows и Linux.

**Architecture:** Парсер сохраняет форматную модель сейва, `editor.equipment` проецирует её в единую release-aware модель оборудования, а Qt/web показывают одну и ту же проекцию и capability maturity. Каждый writer принадлежит конкретному формату/профилю и включается только после differential evidence и game load/re-save. Steam Cloud остаётся отдельным транспортом с provenance, исходным remote path и fail-closed transaction; публикация и OTA используют один подписанный/хэшированный manifest, но не смешивают installer и portable пакеты.

**Tech Stack:** Python 3.11+, PySide6/Qt, pytest, существующий Kraken/X-Ray/S2 codec, web bundle, GitHub Actions, Cloudflare Worker/R2, Debian packaging, PyInstaller/portable archives.

**Spec:** `docs/specs/EQUIPMENT_EDITOR.md`, `docs/superpowers/specs/2026-09-19-s2-equipment-state-design.md`, `docs/superpowers/specs/2026-09-20-portable-updater-r2-release-design.md`, `docs/superpowers/specs/2026-09-18-v0.5.0-native-cloud-and-ui-design.md`, `docs/evidence/S2_EQUIPMENT_WRITER_2026-09-19.md`, `docs/STATUS.md`.

## Global Constraints

- Личные сейвы из `/home/dmytro/Downloads`, Steam Cloud и NVIDIA Now не добавляются в Git. В evidence фиксируются только SHA-256, размеры, агрегированные наблюдения и обезличенные fixture bytes, если они синтетические.
- Ни один S2 writer не выбирает поле по «похожему f32», имени из CFG или prototype SID. Нужны точный differential anchor, проверки handle/границ, container round-trip и game load/re-save.
- `Unknown`/`Неизвестно` остаётся честным значением. Название, иконка, категория и наличие в каталоге не доказывают владение предметом в конкретном сейве.
- `Binoculars_*`, `NVG_Gen2` и другие записи только из name table не показываются как owned inventory rows. Реально найденные actor/grid rows, например `NVG_NPC_Gen3`, проходят отдельную классификацию устройства.
- Для S2 отношения/группировки не показываются, пока нет подтверждённого parser/writer. В коде не остаётся скрытого вызова faction UI для `stalker2`.
- Backups, source-SHA, CRC/Kraken verification, recovery и stale-preview guards остаются внутренними гарантиями одного Save flow; пользователь видит одну кнопку Save и одно подтверждение.
- Cloud upload пишет только выбранный исходный `Data/<slot>.sav`. `-edited.sav`, recovery-файл, TempCampaigns sidecar и локальный cache artifact не становятся cloud target.
- Нельзя объявлять live Steam Cloud write, OTA, GitHub Release, R2 или Pages рабочими только по локальным тестам. Каждый внешний gate получает отдельную read-back проверку.
- Merge, push, rebase, force-push, публикация с неподтверждёнными секретами и изменение `main` выполняются только после отдельного разрешения владельца.

## Review Focus

- Сохраняется ли различие между owned item, metadata/name-table record, available upgrade и installed/current upgrade.
- Не превращается ли неизвестная прочность в ложные `0%`, и не активируется ли editor control для устройств без condition.
- Не используется ли общий S2 armor anchor для оружия, модулей, ПНВ или бинокля.
- Не теряется ли release/edition при переходе из local/cloud inspection в Equipment projection и обратно в `EditPlan`.
- Не меняет ли UI staged edit после сортировки/фильтрации другой handle.
- Не уходит ли upload в `-edited.sav`, старый remote locator, cache-only backend или stale preview.
- Не уезжают ли в релиз старые 15 MB repack-и, смешанные названия `S.T.A.L.K.E.R. 2 Save Editor` и битые ссылки на portable packages.

---

## 0. Canonical scope and evidence inventory

### Task 0.1: Make this document the execution source of truth

**Files:**

- Modify: `docs/README.md`
- Reference, do not duplicate: `docs/superpowers/plans/2026-09-19-s2-equipment-writer.md`
- Reference, do not duplicate: `docs/superpowers/plans/2026-09-19-equipment-editor.md`
- Reference, do not duplicate: `docs/superpowers/plans/2026-09-20-portable-updater-r2-release-plan.md`
- Reference, do not duplicate: `docs/superpowers/plans/2026-09-21-cloud-diagnostics-ota-fix.md`
- Reference, do not duplicate: `docs/superpowers/plans/2026-09-21-maintainability-hardening.md`

**Steps:**

- [x] Add this plan under `docs/README.md` → “Актуальные документы” with an explicit note that the older plans are historical subplans and this file owns ordering and gates.
- [x] At the beginning of implementation, record the current branch, exact HEAD SHA, dirty status and existing release/version in the current status/build evidence.
- [ ] Do not delete old plans until all references and accepted evidence have been migrated; after implementation, archive only documents that no longer describe an active gate.

**Verification:** `python3 -m pytest -q tests/test_docs_consistency.py`; `git diff --check`; `git status --short --branch`.

### Task 0.2: Add an anonymized S2 equipment corpus report

**Files:**

- Create: `docs/evidence/S2_EQUIPMENT_CORPUS_2026-09-22.md`
- Modify: `tools/research_equipment.py`
- Modify: `tests/test_equipment_research.py`
- Test fixtures: `tests/fixtures/` only; never copy personal save files.

**Steps:**

- [x] Make the research command accept an explicit input root and a report/output path, run read-only, and fail if an input file changes in bytes, size or `mtime_ns`.
- [x] Record only file count, accepted/rejected count, SHA-256, packed/raw size, detected release, item category totals, actor/grid/equipped counts and condition-anchor status.
- [x] Record the observed S2 facts needed by later tasks: full Data saves are about 6.6 MB packed; raw payload is about 26 MB; the supplied saves contain armor condition observations and weapon/device/module rows; `Binoculars_*`/`NVG_Gen2` occur in name metadata but are not actor inventory rows.
- [x] Add a synthetic fixture that proves a metadata-only device name cannot create an inventory item.
- [x] Link the report from `docs/README.md` and `docs/STATUS.md` only after the report contains no personal paths or save bytes.

**Verification:** `python3 -m pytest -q tests/test_equipment_research.py tests/test_s2_name_table.py`; run the read-only corpus command against a temporary copy; compare input SHA/size/mtime before and after.

**Gate:** This task documents observations. It does not enable a new writer.

## 1. Shared equipment model and S2 read-only projection

### Task 1.1: Extend the shared model to represent real categories without fabricating support

**Files:**

- Modify: `editor/equipment.py`
- Modify: `editor/catalog.py`
- Modify: `editor/capability_types.py`
- Modify: `tests/test_equipment.py`
- Modify: `tests/test_catalog.py`

**Steps:**

- [x] Extend the product category vocabulary from weapon/armor/helmet/other to include read-only `module`, `device`, `consumable`, `ammo`, `artifact`, `quest` and an explicit `other` fallback; preserve serialization compatibility for existing X-Ray rows.
- [x] Add an explicit device subtype/provenance field to the shared projection so `nvg`, `binocular`, `detector` and unknown devices can be displayed without pretending they have durability.
- [x] Keep `EquipmentSupport` feature-scoped: durability, upgrades, placement, add and remove remain independent maturity values. A read-only category must not inherit a writable capability from its parent item.
- [x] Represent upgrade/module observations as `installed`, `available`, `applicable` or `unknown` only when the parser has evidence; otherwise render the list as observed-but-unclassified metadata.
- [x] Make `as_dict()` stable for Qt/web parity and add compatibility defaults so existing fixtures constructing `EquipmentItem` continue to work.

**Verification:** unit tests cover every category, unknown fallback, device subtype, support maturity and JSON projection; `mypy` must reject an unhandled category label in the UI model.

### Task 1.2: Parse S2 equipment/modules/devices without confusing metadata with owned rows

**Files:**

- Modify: `save_format.py`
- Modify: `editor/s2_catalog.py`
- Modify: `editor/s2_mapping.py`
- Modify: `editor/catalog_bundle.py`
- Modify: `editor/equipment.py`
- Modify: `tests/test_s2_equipment_inventory.py`
- Modify: `tests/test_s2_catalog.py`
- Modify: `tests/test_s2_mapping.py`
- Modify: `tests/test_equipment.py`

**Steps:**

- [x] Keep actor-owned/grid/placed rows as the only source for owned equipment. Keep embedded name-table and CFG records as resolution metadata.
- [x] Classify S2 weapon and armor rows through exact save-local/catalog metadata, not only `kind` or a nearby scalar. Preserve `Unknown` for unresolved names.
- [x] Classify observed `*_Upgrade_*`, attachment/module records and catalog upgrade metadata as `module`/upgrade observations. Do not mark them installed/current unless a controlled pair separates those states.
- [x] Classify actual `NVG_*`, `Binoculars_*` and related rows as devices only when they appear in an owned/grid/equipped record. Attach a device subtype and slot/placement observation if the save provides one.
- [x] Do not assign a durability value or a repair control to devices. A missing condition is `None`/unknown, never numeric zero.
- [x] Keep S2 faction/relationship data outside this projection and retain the current no-faction UI guard.
- [x] Add parser diagnostics that state whether a row came from actor inventory, grid, equipped-owned record, name table or catalog-only metadata.

**Verification:** fixture tests assert that `NVG_NPC_Gen3` is a device when owned, `Binoculars_*` name-table entries do not become rows, modules remain read-only, the generic source-backed weapon condition codec is experimental/read-write for accepted owned rows, and no S2 faction panel is populated.

**Gate:** The read-only S2 equipment projection and source-backed experimental weapon/armor condition codec may ship after the local test gate. This does not unlock module/upgrade, add-item or device writers.

### Task 1.3: Populate S2 names and icons from Zone Kit/official/Workshop metadata safely

**Files:**

- Modify: `editor/s2_catalog.py`
- Modify: `editor/xray_assets.py`
- Modify: `ui/inventory_view.py`
- Modify: `ui/equipment_view.py`
- Modify: `tests/test_s2_catalog.py`
- Modify: `tests/test_ui_inventory_icons.py`
- Modify: `tests/test_cross_game_icons.py`
- Modify: `tests/test_web_inventory_icons.py`

**Steps:**

- [x] Keep official loose CFG/localization as the authoritative installed-game source; treat explicitly selected Zone Kit and Workshop trees as provenance-labeled research/presentation sources.
- [x] Resolve localized display names and icon texture references for weapons, armor, modules and devices, including the S2 device rows observed in the corpus.
- [x] Never unpack arbitrary PAKs, execute Workshop content or let a mod override silently become official save metadata.
- [x] Use a category glyph and `Unknown · <handle>` fallback when the actual texture/name is unavailable; do not show blank cells or invented names.
- [x] Ensure icon resolution is presentation-only and cannot affect save editing, row identity or capability maturity.

**Verification:** Qt and web tests use the same catalog projection; tests cover missing resource, mod-overlay provenance, DDS/PNG/JPG/WebP/BMP references, device icons and a real fallback glyph.

## 2. Controlled S2 condition evidence and weapon writer

### Task 2.1: Capture and analyze a controlled weapon condition pair

**External input required from the user:** two copies of the same S2 save, before and after exactly one weapon-condition change; each copy must be loaded/resaved by the game after the action.

**Files:**

- Modify: `tools/research_equipment.py`
- Create or modify: `tools/research_s2_equipment_pair.py`
- Modify: `tests/test_equipment_research.py`
- Create: `docs/evidence/S2_WEAPON_CONDITION_PAIR_<date>.md` after the pair is supplied.

**Steps:**

- [ ] Preserve original SHA-256 and immutable copies outside the live Steam Cloud slot.
- [ ] Require the pair manifest to identify the same weapon, exact in-game action, save slot names, game load/resave step and whether unrelated inventory/quest/equipment changes occurred.
- [ ] Decompress both files and correlate the same actor-owned weapon by handle, type/name and object graph.
- [ ] Produce a bounded binary diff with candidate offsets, field widths, before/after values and all unrelated changed regions classified. A candidate is accepted only if the changed field follows the weapon through another game save and no second candidate changes with it.
- [ ] Compare the candidate against armor/device/module records so a generic scalar cannot be promoted to a weapon condition anchor.
- [ ] If no unique field survives the pair, record the result as research and leave the writer disabled; do not “pick the closest” field.

**Verification:** the tool is deterministic on a synthetic pair, never writes input files, rejects mismatched handles/releases, and emits enough evidence for an independent review.

**Gate:** No code that writes weapon condition is allowed before a unique anchor and game read-back are documented.

**Current evidence:** `docs/evidence/S2_WEAPON_MODULE_CORPUS_2026-09-22.md`
records a strong Kharod read candidate at `record + 0x190` (`88.45%` and
`92.51%` across the supplied pair), a corroborating but unchanged Lavina value
at `record + 0x199` (`39.42%`), and the fact that the supplied D-12 records are
not actor-owned rows. This advances Kharod from “no candidate” to “research /
strong candidate”; it does not pass game acceptance or unlock a universal
weapon writer.

### Task 2.2: Implement the weapon condition transaction only if Task 2.1 passes

**Files if the gate passes:**

- Modify: `editor/s2_item_state.py`
- Modify: `save_format.py`
- Modify: `editor/formats.py`
- Modify: `editor/capabilities.py`
- Modify: `editor/prepare.py`
- Modify: `ui/inventory_view.py`
- Modify: `ui/equipment_view.py`
- Modify: `tests/test_s2_item_state.py`
- Modify: `tests/test_s2_durability.py`
- Modify: `tests/test_s2_equipment_inventory.py`
- Modify: `tests/test_ui_inventory.py`
- Modify: `tests/test_ui_equipment.py`

**Steps:**

- [x] Add a named weapon anchor/codec separate from the armor anchor; validate kind, handle, record boundaries, finite range and exact byte width.
- [x] Carry weapon condition through immutable `EditPlan.durability` and the existing rebuild path; after rebuild, decode every requested value and reject mismatch.
- [x] Expose `Восстановить до 100%`/percentage editing only for rows whose exact weapon capability is present. Devices, modules and unresolved rows remain read-only.
- [x] Keep the one-click Save flow: one confirmation, internal preview/backup/CRC/SHA/recovery, then local output or Cloud upload.
- [ ] Start with `experimental`; upgrade to `verified` only after the edited save is loaded and re-saved by the game with the expected condition preserved.

**Verification:** exact-offset codec tests, stale-source rejection, transaction round-trip, game re-save evidence and a regression test proving armor/device behavior is unchanged.

**Gate if Task 2.1 fails:** update the capability reason/evidence only; ship read-only weapon rows rather than a speculative writer.

## 3. Modules, upgrades, PNV and binocular semantics

### Task 3.1: Separate observed modules/upgrades from installed/current state

**Files:**

- Modify: `editor/s2_catalog.py`
- Modify: `editor/equipment.py`
- Modify: `save_format.py`
- Modify: `tests/test_s2_catalog.py`
- Modify: `tests/test_s2_equipment_inventory.py`
- Modify: `tests/test_ui_upgrades.py`
- Modify: `tests/test_web_upgrades.py`

**External input required for a writer:** a before/after pair with exactly one in-game upgrade installation (and a second pair for removal if removal is intended).

**Steps:**

- [x] Display catalog applicability separately from save-observed upgrade references.
- [x] Label each upgrade as installed/current, available/applicable or unknown only when the structure proves that state; otherwise show “обнаружено, состояние не подтверждено”.
- [x] Keep S2 upgrade mutation disabled until the pair identifies all affected references, vector boundaries and game acceptance.
- [x] Treat direct weapon module references (magazine, optic, suppressor, grenade launcher, rail, grip, laser and weapon-specific attachment families) as a separate read-only projection from the duplicated upgrade-key vectors.
- [x] Add per-weapon module families from the observed save/catalog data; do not expose a universal module list when a game or weapon lacks that slot.
- [x] For X-Ray original profiles, retain existing independent upgrade capabilities and tests; never let S2 maturity changes alter SoC/CS/CoP behavior.
- [ ] If the controlled S2 pair passes, add a format-specific transaction and re-run the same backup/CRC/SHA/game read-back gates as durability.

**Verification:** tests prove that a catalog-only upgrade cannot be staged, an observed but unclassified array is read-only, and existing X-Ray upgrade tests remain green.

### Task 3.2: Determine S2 device placement without inventing durability

**Files:**

- Modify: `editor/equipment.py`
- Modify: `save_format.py`
- Modify: `ui/inventory_model.py`
- Modify: `ui/inventory_view.py`
- Modify: `tests/test_s2_equipment_inventory.py`
- Modify: `tests/test_ui_inventory.py`

**External input required only if the corpus cannot distinguish placement:** one save with the device in inventory, one with it equipped/selected in the actual S2 slot, and one after game resave.

**Steps:**

- [x] Use the actual observed storage/placement/reference fields to distinguish inventory, belt/quick slot, equipped module or device slot; do not map every non-grid record to `equipped`.
- [x] Render PNV and binocular as devices with slot/placement text, no percentage editor, no repair action and no fabricated condition.
- [x] Keep `Binoculars_*`/`NVG_Gen2` metadata-only unless a real owned row appears.
- [x] Document the result in the corpus evidence and add fixtures for each distinct placement state.

**Gate:** placement may be shown read-only after parser evidence; device write support is out of scope for this pass.

## 4. Cross-game equipment matrix and Enhanced Editions

### Task 4.1: Verify per-game equipment capabilities instead of sharing S2 assumptions

**Files:**

- Modify: `editor/releases.py`
- Modify: `editor/formats.py`
- Modify: `editor/equipment.py`
- Modify: `editor/xray_catalog.py`
- Modify: `editor/xray_save.py`
- Modify: `tests/test_releases.py`
- Modify: `tests/test_xray_durability.py`
- Modify: `tests/test_xray_upgrades.py`
- Modify: `tests/test_equipment.py`
- Create: `docs/evidence/EQUIPMENT_SUPPORT_MATRIX_2026-09-22.md`

**Steps:**

- [x] Build a matrix for SoC, Clear Sky, Call of Pripyat, each Enhanced Edition profile and S2 covering weapon condition, armor condition, helmets, upgrades, modules, devices, placement, add/remove, faction UI and icon/name source.
- [x] Keep SoC’s lack of confirmed upgrade editing explicit. Do not display an upgrade control because another X-Ray profile supports one.
- [x] Verify weapon/armor repair and upgrade capability independently for Clear Sky and Call of Pripyat; separate original and Enhanced Edition parser/capability IDs.
- [x] Treat Enhanced Editions as unsupported/research until an actual sample is supplied and format detection/parser behavior is proven. The current S2 work must not wait for those files.
- [x] Make UI labels and capability reasons come from this matrix/registry rather than scattered conditionals.

**Verification:** capability matrix tests assert every release/edition, no Enhanced Edition is detected as original by accident, and no category control is shown outside its profile.

### Task 4.2: Consolidate catalog and capability registry

**Files:**

- Modify: `editor/capabilities.py`
- Modify: `editor/releases.py`
- Modify: `editor/catalog_bundle.py`
- Modify: `editor/formats.py`
- Modify: `tests/test_capabilities.py`
- Modify: `tests/test_formats.py`
- Modify: `tests/test_service_parity.py`

**Steps:**

- [x] Define one release/edition registry consumed by parser, catalog, UI and web bridge; package metadata remains product-level and does not duplicate release claims.
- [x] Remove duplicate ad-hoc release/category capability declarations where the registry can supply the same value without changing behavior.
- [x] Keep maturity reasons and evidence references machine-readable so UI can explain “read-only” without exposing internal paths or speculative claims.
- [x] Add parity tests that compare the shared Qt/web equipment JSON projection for categories, device subtype, icons, names and capabilities.

## 5. Unified UI and S.T.A.L.K.E.R.-2 visual language

### Task 5.1: Make the equipment surface one navigable, human workflow

**Files:**

- Modify: `ui/main_window.py`
- Modify: `ui/inventory_view.py`
- Modify: `ui/equipment_view.py`
- Modify: `ui/equipment_model.py`
- Modify: `ui/inventory_model.py`
- Modify: `ui/changes_view.py`
- Modify: `ui/backups_view.py`
- Modify: `tests/test_ui_equipment.py`
- Modify: `tests/test_ui_inventory.py`
- Modify: `tests/test_ui_apply.py`
- Modify: `tests/test_ui_backups.py`
- Modify: `tests/test_ui_switcher.py`

**Steps:**

- [x] Preserve the fast launcher and in-editor game/save switcher, but remove user-visible duplicate Preview/Changes/Backups choreography from the normal edit path.
- [x] Keep one Save button and one confirmation. The dialog states the selected game/save, operation count, automatic backup/recovery and destination; after confirmation the internal pipeline performs preview, backup, write and read-back.
- [x] Keep advanced Changes/Backups views available for inspection/recovery, but make them secondary tools rather than mandatory tabs for a normal edit.
- [x] Show category, location, condition support and module/device state in one consistent table; sort/filter by stable handle, never by row position.
- [x] Hide irrelevant controls: S2 faction relations, device durability, unsupported Enhanced Edition writers and unconfirmed upgrade/add-item actions.
- [x] Use human labels such as “Прочность”, “Состояние модуля”, “Устройство/слот” and “Не подтверждено”, with exact type-key/handle in tooltip.

**Verification:** Qt tests cover one confirmation, automatic backup, stale preview, cancel, successful local save, Cloud-specific confirmation and disabled controls for unsupported categories.

### Task 5.2: Replace mixed Zone/milk visual language with one S2-inspired theme

**Files:**

- Modify: `ui/theme.py`
- Modify: `ui/main_window.py`
- Modify: `ui/launcher_view.py`
- Modify: `ui/inventory_view.py`
- Modify: `ui/equipment_view.py`
- Modify: `ui/cloud_view.py`
- Modify: `tests/test_ui_theme.py`
- Modify: `tools/export_theme.py`

**Steps:**

- [x] Define one tokenized palette, typography scale, spacing, focus state, warning/error state and panel hierarchy inspired by S.T.A.L.K.E.R. 2 without mixing unrelated legacy panels.
- [x] Apply the same tokens to launcher, workbench, equipment, inventory, Cloud, updates and diagnostics; remove local one-off stylesheet colors that override the design system.
- [x] Preserve readable contrast for status text, warnings and disabled/read-only controls; verify long paths and Russian/English labels do not disappear into the background.
- [x] Keep icons and labels data-driven by release/catalog, with stable fallback glyphs.

**Verification:** theme tests, Qt smoke screenshots at the supported desktop sizes, contrast/visibility assertions for status/error labels and web/Qt token parity.

## 6. Steam Cloud, repack and diagnostics

### Task 6.1: Make Cloud target/provenance/repack behavior deterministic

**Files:**

- Modify: `steam_cloud.py`
- Modify: `editor/steam_backend.py`
- Modify: `editor/steam_native.py`
- Modify: `editor/steam_cdp.py`
- Modify: `editor/steam_profiles.py`
- Modify: `editor/transactions.py`
- Modify: `ui/cloud_view.py`
- Modify: `tests/test_steam_profiles.py`
- Modify: `tests/test_steam_native_subprocess.py`
- Modify: `tests/test_steam_cdp.py`
- Modify: `tests/test_cloud_transaction.py`
- Modify: `tests/test_ui_cloud.py`
- Modify: `tests/test_compact_rebuild.py`

**Steps:**

- [x] Keep only `Stalker2/Saved/STEAM/SaveGames/Data/*.sav` in the S2 editable Cloud picker; show TempCampaigns sidecars as unsupported metadata or omit them with an explanation.
- [x] Preserve the exact selected remote path and backend provenance from list → read → inspect → prepare → write. Never reconstruct a target from the local edited filename.
- [x] Reject `-edited.sav`, recovery and cache-only paths before any write. Never retry an uncertain write automatically.
- [x] Keep native initialization and writer capability independent from `GetFileCount() == 0`; retain the `FileWrite` path when remote listing came from cache/web and the native writer is positively initialized.
- [x] Repack edited S2 saves with the compact Kraken path that produced the normal approximately 6–7 MB output, not the 15 MB stored-block fallback. Verify unpacked bytes, CRC and fresh SHA before upload.
- [x] After upload, read back the same remote path and compare size/SHA/persistence metadata. An uncertain result is shown as uncertain and leaves the local recovery artifact.

**Verification:** transaction tests cover stale remote locator, selected original path, `-edited` rejection, compact repack size/round-trip, native writer capability, read-back mismatch and no automatic retry.

**External gate:** live Steam Cloud write/read-back and game load are recorded separately from local tests.

### Task 6.2: Keep logs bounded, useful and sendable

**Files:**

- Modify: `editor/diagnostics.py`
- Modify: `ui/diagnostics_dialog.py`
- Modify: `ui/main_window.py`
- Modify: `infra/downloads-worker/worker.js`
- Modify: `infra/downloads-worker/wrangler.toml`
- Modify: `infra/downloads-worker/lifecycle.json`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_diagnostic_cli.py`
- Modify: `tests/test_ui_cloud.py`
- Modify: `tests/js/downloads-worker.test.mjs`

**Steps:**

- [x] Rotate local logs by size/count and retain a bounded age/total budget; expose a cleanup operation without touching saves or backups.
- [x] Redact home paths, Steam account identifiers, tokens, save bytes, cookies and arbitrary file contents while retaining operation, backend, release, sizes, hashes and exception class.
- [x] Add one “Отправить логи” action that previews the redacted bundle, uses a random diagnostic object id, enforces a body limit and reports the received id/status.
- [x] Configure R2 lifecycle expiry for diagnostics and test no-cache/error responses; do not mix diagnostic objects with release artifacts.
- [x] Make upload failure non-blocking and keep a local export path for manual attachment.

**Verification:** redaction/rotation/size tests, Worker integration tests, UI tests for send success/failure and a check that diagnostic bundles contain no save bytes or credentials.

## 7. Code quality, dead code and performance pass

### Task 7.1: Refactor only after behavior gates are covered

**Files:**

- Review all Python under `editor/`, `ui/`, `tools/`, `packaging/`
- Review web code under `web/` and `infra/`
- Modify only files with an evidence-backed finding.
- Add focused tests beside each removed/rewritten path.

**Steps:**

- [x] Use `ruff`, `mypy`, `pytest --cov`/coverage output already supported by the repository, import/compile checks and JavaScript tests to find dead branches, duplicate registries, unreachable UI actions and unused compatibility code.
- [x] Consolidate repeated release/category/icon/capability formatting behind the shared model without moving binary parsing into the UI.
- [x] Keep large save decompression, catalog scans, Steam native calls and Cloud operations off the Qt main thread; use bounded child-process containment for native calls that can hang.
- [x] Cache only immutable source-scoped catalog/locale results; invalidate explicit Zone Kit/Workshop selections and never cache a user’s mutable save bytes as authoritative metadata.
- [x] Remove dead code only when `rg` plus tests show no import, entrypoint, workflow or documented interface uses it. Preserve public compatibility shims until callers are migrated.
- [x] Add regression tests for every optimized parser/catalog/cloud path and compare before/after output on the synthetic corpus.

**Verification:** `ruff check .`, `mypy .` or the repository’s configured mypy target, `python3 -m compileall editor ui tools packaging`, all Python tests, all JS tests and web bundle checks.

### Task 7.2: Rename product/package surfaces consistently

**Files:**

- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `packaging/editor.spec`
- Modify: `packaging/gui_entry.py`
- Modify: `packaging/native_entry.py`
- Modify: `packaging/com.github.dmitriyde.stalker2saveeditor.metainfo.xml`
- Modify: `Makefile`
- Modify: `.github/workflows/build.yml`
- Modify: web metadata/download labels and tests.

**Steps:**

- [x] Use product name `S.T.A.L.K.E.R. Save Editor` in window title, package display name, installer labels, release notes and download cards; keep historical repository/package identifiers only where a platform requires them.
- [x] Ensure claims say “supports …” only for profiles in the capability registry, not “S.T.A.L.K.E.R. 2 only”.
- [x] Update help/status text to explain that a device has no durability and that upgrades are read-only when their serializer is unconfirmed.
- [ ] Remove stale v0.5.14/v0.5.20 instructions and links only after the replacement release evidence is available.

**Verification:** packaging and docs consistency tests; grep for stale product labels and old download filenames; run the packaged app’s `--version`/metadata smoke test.

## 8. Portable builds, OTA, GitHub/R2 and website

### Task 8.1: Build separate installer and portable artifacts

**Files:**

- Modify: `packaging/build.py`
- Modify: `packaging/editor.spec`
- Modify: `editor/release_artifacts.py`
- Modify: `editor/update_manifest.py`
- Modify: `tools/build_release_manifest.py`
- Modify: `tests/test_packaging.py`
- Modify: `tests/test_release_manifest_tool.py`
- Modify: `tests/test_update_manifest.py`
- Modify: `Makefile`
- Modify: `.github/workflows/build.yml`

**Steps:**

- [x] Produce distinct Windows installer and Windows portable ZIP artifacts.
- [x] Produce distinct Linux `.deb` installer and Linux portable `.tar.gz` artifacts.
- [x] Give every artifact platform, architecture, install kind, version, size and SHA-256 in one manifest; do not infer portable/installer from a filename in the updater.
- [x] Put the updater in every supported desktop/portable package with a safe external handoff: `.deb`/installer to OS installer flow, portable archive to the existing replacement helper.
- [ ] Test first launch from a clean directory, upgrade preserving user data, rollback/recovery on failed extraction, and no writing into the repository or game save directory.

**Verification:** local package build, archive listing, install/launch smoke, updater unit tests and manifest hash verification for all four artifact classes.

### Task 8.2: Publish and read back GitHub Release/R2/APT/Pages

**Files:**

- Modify: `tools/publish_release.py`
- Modify: `tools/build_apt_repo.py`
- Modify: `tools/verify_apt_repo.py`
- Modify: `infra/downloads-worker/worker.js`
- Modify: `.github/workflows/build.yml`
- Modify: web download manifest/cards and tests.

**Steps:**

- [ ] Build release artifacts once and publish the exact same bytes to GitHub Release and R2; do not rebuild between destinations.
- [ ] Publish `latest.json`/manifest, checksums and separate installer/portable entries; verify every advertised URL, content length, SHA-256 and content disposition by read-back.
- [ ] Update the Cloudflare Worker/R2 objects used by the website, then verify the public Pages download links return the new manifest and correct artifact.
- [ ] Publish Debian/APT metadata only when signing key configuration is available; otherwise report APT as blocked without faking a successful repository update.
- [ ] Verify OTA from an older installed Linux/Windows/portable build against the public manifest, including version comparison, host allow-list and SHA/size checks.

**External gate:** public publication requires credentials/connectors and a read-back from the actual GitHub/R2/Pages endpoints; local workflow success alone is insufficient.

## 9. Final verification, cleanup and handoff

### Task 9.1: Run the complete quality/release gate

**Files:**

- Modify: `docs/STATUS.md`
- Modify: `docs/RELEASE.md`
- Modify: `docs/evidence/` with dated evidence files.

**Steps:**

- [x] Run focused S2/equipment tests first, then the complete Python suite, JS tests, web build/check, type/lint/compile checks and package smoke tests.
- [x] Run the read-only local-save corpus scan and verify all input hashes/mtimes remain unchanged.
- [x] Run the local Cloud transaction matrix with fake transports; the external Steam Cloud write/read-back gate remains separate and unchecked.
- [ ] Run user-controlled game load/re-save for each newly enabled writer: S2 armor, S2 weapon if accepted, S2 upgrade if accepted, and the existing X-Ray writers whose status is being upgraded.
- [ ] Build all four desktop artifact classes, generate the manifest, publish only with permission, read back GitHub/R2/Pages, and record exact commit/artifact SHA-256 values.
- [x] Update `docs/STATUS.md` with separate statuses for local tests, CI, game acceptance, Steam Cloud live write, GitHub, R2, Pages, APT and OTA.

**Verification command set:** `make check`, `make test`, `make web`, `make package`, `make release-manifest`, package-specific smoke tests, and the repository’s configured CI-equivalent commands. Record actual output, not a green claim without output.

### Task 9.2: Clean only task-owned residue

**Files/locations:**

- Review: repository branches/worktrees, `.pytest_cache`, `__pycache__`, temporary build directories, generated release staging directories and task-created logs.
- Preserve: source, docs, build artifacts intended for release, public evidence, user saves, Steam Cloud, backups and unrelated user work.

**Steps:**

- [x] List before deletion; remove only generated caches/temp files proven to belong to this task.
- [x] Remove stale `-edited.sav`/diagnostic artifacts only from task-owned temporary staging, never from the user’s Steam Cloud or backup roots.
- [x] Do not use destructive repository commands (`reset --hard`, broad recursive deletion, branch deletion) without an exact target and owner approval.
- [x] Leave the working tree clean except for intentional source/docs changes, and report every removed class of residue.

**Verification:** `git status --short --branch`, `git worktree list`, `git branch --list`, `git diff --check`, repository file audit and a final no-personal-saves-in-Git scan.

### Task 9.3: Fresh-context review and closure

**Steps:**

- [x] Review the final diff in a fresh context against this plan, `docs/STATUS.md`, the capability matrix and the current release manifest.
- [x] Fix every actionable finding that affects correctness, safety, UX, performance, packaging or documentation, then rerun the affected gate.
- [x] State explicitly which capabilities are `verified`, `experimental`, `research` and `unsupported`.
- [x] State explicitly whether GitHub Release, R2, Pages, APT, OTA, Steam Cloud live write and game load/re-save were externally verified.
- [x] Stop at the first missing external gate instead of calling the project “done”; provide the exact next evidence required.

## Execution order and required user inputs

1. Tasks 0–1: consolidate docs, record the new corpus and ship/verify read-only equipment/modules/devices projection.
2. Task 5: unify the surface so every later writer uses one Save flow and one visual language.
3. Task 6: finish Cloud target/provenance/repack/diagnostics before any live upload test.
4. Task 2: user supplies the controlled weapon condition pair; writer is implemented only if the evidence gate passes.
5. Task 3: classify PNV/binocular placement from current saves; user supplies a placement pair only if the current corpus cannot distinguish it. Upgrade writer remains gated by its own pair.
6. Task 4: verify the cross-game matrix; Enhanced Edition files can be supplied later and do not block S2 read-only work.
7. Tasks 7–9: quality pass, separate builds, public publication/read-back, OTA verification, cleanup and fresh-context review.

The next external inputs are therefore precise:

- **Weapon condition:** `before` and `after` full S2 Data saves with one known weapon condition change and a game load/resave after the change.
- **S2 upgrade writer, if wanted:** `before` and `after` saves with exactly one upgrade installation, plus a removal pair if removal is required.
- **PNV/binocular placement, only if needed:** saves showing the same device in each distinct actual S2 placement state.
- **Enhanced Editions:** one real save per edition when available; no need to block current S2 work.

Until those files arrive, implementation can proceed through read-only parsing, categories, names/icons, unified UI, Cloud/repack, diagnostics, tests and builds. No speculative condition/upgrades/device writer is part of the safe baseline.
