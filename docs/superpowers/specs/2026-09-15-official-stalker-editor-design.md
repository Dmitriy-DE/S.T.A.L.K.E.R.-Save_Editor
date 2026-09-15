# Official S.T.A.L.K.E.R. Save Editor Design

**Date:** 2026-09-15  
**Status:** Proposed; approved in chat, pending written-spec review  
**Scope:** Official PC releases only; community mods are explicitly out of scope.

## Goal

Provide one Qt desktop application and one static browser application for the
four official S.T.A.L.K.E.R. game families in scope:

- S.T.A.L.K.E.R. 2: Heart of Chornobyl;
- S.T.A.L.K.E.R.: Shadow of Chernobyl;
- S.T.A.L.K.E.R.: Clear Sky;
- S.T.A.L.K.E.R.: Call of Pripyat;
- and the official Enhanced Editions of the three original games where their
  real save format is separately verified.

The user must be able to select a game/release, let the desktop app search
known standard save locations, choose a manual folder or file, inspect a save,
edit the supported inventory state, and export a new save copy. The browser
must expose the same parser and writer through local file selection and
download; browser security means it cannot scan the user's folders.

“Any save” means any unmodified save from a supported official release/build
covered by the evidence matrix. An unknown version, modded save, or
unverified Enhanced format is visible as unsupported/read-only rather than
being guessed into a supported format.

## Evidence and domain boundaries

The existing local corpus contains original X-Ray saves for all three classic
games. Their current observed container/actor tuples are SoC `3/118`, CS
`5/124`, and CoP `6/128`; the public [Universal-ACDC version table](https://github.com/PSIget/Universal-ACDC)
lists the broader official patch ranges. Public X-Ray tooling also treats saves
and game configuration as related but distinct data: see the
[stalker-tools repository](https://github.com/stalker-tools/tools) and
[OpenXRay serialization sources](https://github.com/joedemo42/OpenXRay).

No Enhanced Edition save or installation is present in the current machine's
read-only inventory. Reports indicate that EE save names and/or sidecars can
diverge from the original releases, including `.scs` reports for Clear Sky;
the [SoC EE discussion](https://steamcommunity.com/app/2427410/discussions/0/528723757459612258/)
and [CS EE discussion](https://steamcommunity.com/app/2427420/discussions/0/603030907426702266/?l=ukrainian)
are leads, not format acceptance evidence. Enhanced support therefore requires
an external corpus before implementation is called complete.

Game binaries, private saves, screenshots, credentials, and personal catalogs
must remain outside Git. The desktop may read an installed official game tree
read-only; the web bundle may contain only deliberately generated metadata and
schemas, never copied game archives.

## Design

### 1. One shared format contract

Keep the UI-free `EditorService` as the only orchestration boundary. Extend the
existing `SaveFormat` registry with release metadata and explicit capabilities,
without moving format parsing into Qt or JavaScript.

Conceptually each registered profile provides:

```text
release_id/title/edition
detect(bytes) -> strict content result
inspect(bytes, with_inventory) -> SaveInfo
capabilities() -> read/edit feature flags
catalog(source) -> optional ItemCatalog
prepare(bytes, immutable EditPlan) -> PreparedEdit
```

`detect_fast` remains an optional discovery-only probe. A row discovered by the
fast probe must pass strict detection and full inspection before a preview or
writer operation can be enabled.

The registry will contain separate profiles for:

- S.T.A.L.K.E.R. 2's existing GVAS/Kraken/CRC format;
- original SoC, CS, and CoP X-Ray formats, sharing a container reader only
  where the evidence proves the framing is shared;
- each Enhanced Edition format/version after its container and object schema
  are measured from real files.

An extension such as `.sav` is only a search hint. Content, version, and
edition checks select the profile. Unsupported bytes receive structured
failure reasons.

### 2. Release and save-location model

The existing `InstalledGame`, `save_directories`, and manual settings flow will
be generalized around an explicit release descriptor:

```text
family: s2 | soc | clear_sky | cop
edition: original | enhanced | s2
official_app_id(s)
save_extensions / sidecars
standard location providers
format profile ids
```

Desktop startup shows the four families and detected installed editions. “Auto”
searches all known standard roots and reports every searched root, including
missing roots. Selecting a family or edition narrows the search and prevents a
same-extension file from being attributed to the wrong game. A manual root has
priority for that family/release and never silently falls back while the root
exists.

Discovery remains read-only. It may display `.sav`, `.scop`, `.scs`, or other
known candidate extensions as unsupported, but it never creates directories,
changes Steam files, or writes a game slot.

The web app receives a release selection and a local `File` object. It cannot
use desktop path discovery; it must show that distinction in the UI.

### 3. Inventory/catalog separation

Parsing a save and resolving the complete game item catalog are separate
operations:

- The save parser reads every serialized inventory object, ownership relation,
  handle, state, update packet, and item key that the format proves.
- An `ItemCatalogProvider` resolves the key into display name, category,
  weight, dimensions, stack rules, equipment slots, and the version-specific
  serialization/prototype needed for insertion.
- Desktop may build or load a catalog from the installed official game data
  read-only. Packed archives require a project-owned decoder or a compatible
  provenance-reviewed dependency; game archives are never copied into Git.
- Web uses a compact generated catalog for each accepted official profile. A
  profile without a distributable catalog can still inspect saves but must
  disable “add item” and explain why.

The UI must distinguish `serialized key`, `catalog-resolved name`, and
`unknown`. It must never display a fabricated item name, weight, zero, or
position to fill a missing field.

### 4. Writer and edit capabilities

The shared immutable `EditPlan` remains the only mutation input. Each profile
declares which operations it can prove. The target capability set is:

- money;
- stack counts;
- inventory movement/equipment where the save schema proves the relationship;
- add an item from that release's catalog;
- remove an item;
- durability, upgrades, and attachments only where their serialized fields and
  game semantics are proven.

Adding an item is a format-specific object transaction, not a string patch. It
must allocate a fresh valid handle, serialize the correct object class/state
and update packets, attach the object to the actor, update registry framing and
any format-specific counts/checksums, then rebuild the container.

Every mutating profile must enforce:

1. source SHA freshness;
2. immutable plan validation and range checks;
3. exact no-op preservation when nothing changed;
4. backup/atomic export for desktop and download-only output for web;
5. strict reparse of the produced bytes;
6. fresh output SHA and unchanged-source proof;
7. game-load/re-save evidence before the capability is described as accepted.

If any object allocator, catalog mapping, or version boundary is uncertain,
that operation is disabled rather than approximated.

### 5. Common Qt and web surface

The desktop and browser render the same `SaveInfo`, capability flags, metadata,
inventory rows, warnings, and edit result. UI-specific code only handles:

- release selection and path/file input;
- staged form state;
- worker lifecycle in Qt;
- browser drag/drop and download;
- error and unsupported-format presentation.

The web bundle is regenerated from the Python sources and must continue to
pass the existing generated-artifact checks. No second JavaScript parser or
writer is permitted.

## Acceptance matrix

Acceptance is tracked per official release/build, not as one broad “STALKER
support” checkbox.

For each profile, the evidence row must contain:

1. at least one clean save and, for mutable fields, controlled before/after
   pairs;
2. strict format/version detection and wrong-game rejection;
3. no-op byte/SHA round-trip;
4. full inventory parse with explicit unknown coverage;
5. each enabled edit's in-memory and exported round-trip;
6. load of the exported copy in the matching official game;
7. save again in the game and re-open in the editor;
8. desktop auto/manual path evidence where that platform is claimed;
9. web bridge and download evidence for the same profile.

The current original-trilogy corpus satisfies the container/no-op and partial
reader gates, not full item creation or game-load gates. The three Enhanced
profiles remain blocked until real official EE saves are available.

## Non-goals

- community mods and mod-specific builds;
- Steam Cloud writes from the browser;
- automatic overwrite or restore of a real game slot;
- claiming Windows, cloud, or in-game semantics from Linux unit tests;
- using filename extensions, guessed offsets, or a single matching save as
  proof of a format or field.

## Delivery phases

1. Normalize the release/profile/capability registry and shared desktop/web
   selection flow.
2. Finish the original-trilogy catalog and full object writer against the
   installed official game data and real save corpus.
3. Preserve and integrate the existing S.T.A.L.K.E.R. 2 capabilities under the
   same capability-driven UI.
4. Obtain and characterize one corpus per Enhanced Edition and implement each
   adapter only after its schema is known.
5. Run the complete acceptance matrix, update the current task/status docs, and
   report exact gates, limitations, commit, and PR state.
