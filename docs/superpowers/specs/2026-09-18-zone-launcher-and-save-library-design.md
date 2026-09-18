# Zone Launcher and Save Library Design

**Date:** 2026-09-18  
**Status:** Approved in chat; implementation pending  
**Scope:** Qt desktop launcher and local save discovery for the four supported game families

## Goal

Replace the current dashboard-first Qt shell with a Zone-style launcher in which
the user sees all supported game families and their discovered save slots from
the first screen, can select a game and a save, and can import an arbitrary
local save file even when that game is not installed locally.

The existing parser, `EditorService`, immutable edit plans, CRC/SHA checks,
backup path, atomic export, Cloud state machine, and browser edition remain
the source of truth. This change is a shell and discovery-flow change, not a
new parser or a second UI implementation.

## Current evidence and defect boundary

The current `MainWindow` builds a title bar, metadata bar, sidebar, metric
cards, and hidden tab navigation. The save discovery implementation already
scans all official release selectors and content-detects files, but it is only
reachable through a secondary “Found saves” tab. Installed-release detection
requires a Steam manifest, while the existing orphan-install search can find
classic `_appdata_/savedgames` directories without one. These two facts make
the UI show the wrong default game and hide the saves that the core can already
see.

The new flow must distinguish these independent facts:

- an official game manifest and install directory were found;
- a known save directory exists;
- supported save files were found in that directory;
- the game is absent locally but a user can import a file;
- a candidate file is present but its content is unsupported or unknown.

No status may claim that a game is installed merely because a filename or
extension resembles it.

## User experience

### Launcher

The first page is a single Zone-style scene rather than a SaaS dashboard:

- one dark textured stage using the existing X-Ray chrome assets;
- a restrained title/logo area and technical version marker;
- a narrow vertical game menu with the four families in stable order;
- an adjacent save list for the selected family, with a visible “All games”
  option;
- amber/yellow focus and hover states, rectangular framed controls, and no
  KPI cards, rounded dashboard cards, or persistent “sections” sidebar;
- a prominent `Import save` action and a separate `Refresh` action;
- a compact status line explaining whether the selected game is installed,
  has only save data, or is unavailable locally.

The launcher never opens a file automatically on startup. It scans read-only,
then waits for the user to select a row or import a file. Empty or missing
directories remain visible in the status/search explanation.

Each save row displays the filename, modification time, size, detected game or
release, and a truthful support state. Double-clicking or activating a
supported row uses the same full inspection path as manual file opening.

### Import without an installed game

`Import save` calls the existing content-only `EditorService` inspection path.
The file's bytes, not its extension or parent directory, choose the format and
game. A downloaded S.T.A.L.K.E.R. 2 save therefore remains openable when the
game is absent; installed game data is optional catalog context only. If the
catalog is unavailable, the UI says so and keeps unsupported names/fields
read-only rather than inventing values.

An unsupported or malformed file remains outside the selected game and shows
the shared core detection error. The app never copies it into a game folder,
Steam folder, or Cloud storage as part of import.

### Workbench

After a save is selected, the existing editor capabilities remain available in
a workbench mode. The workbench uses the same X-Ray panel/button palette and
keeps the current safe edit flow. The launcher is the primary navigation entry;
the existing inventory, changes, backup, Cloud, discovery details, and settings
surfaces are retained as secondary workbench pages while their data continues
to come from the current snapshot and capability flags.

## Architecture

### Read-only library model

Add a focused UI-free library/discovery result in `editor/` (or extend the
existing platform discovery boundary without duplicating path rules). It
aggregates the four game families, release descriptors, searched paths,
installed-release observations, and detected save candidates. The result is
immutable and contains no save bytes beyond the existing fast detection step.

The model must reuse `official_releases`, `save_search_paths`, manual settings
priority, and the format registry. It must retain candidate release metadata
for path explanations but only assign a real game/release after content
detection. The Qt layer renders the result and owns worker lifecycle; it does
not implement path or format rules.

The library scan may recognize an orphaned known install/save directory for
launcher status, but must label it as “save data found” or equivalent when a
manifest/executable was not verified. Existing `installed_releases` semantics
remain unchanged for callers that require manifest-backed installations.

### Main window state

Keep one `MainWindow` and one `QStackedWidget` or equivalent mode boundary:

- launcher state: library result, selected family, selected slot;
- workbench state: the existing `LocalSnapshot`, staged edits, preview, and
  operation lifecycle.

The manual file picker, discovered-slot activation, and any future Cloud local
download must converge on `_start_inspect`. A successful inspection updates the
selected launcher game from the detected `release_id` and switches to the
workbench. Returning to the launcher does not discard the snapshot unless the
user explicitly opens another source.

The current public test-facing widget attributes should be preserved where
practical, or replaced with a narrow compatibility alias, so existing editor
tests do not become coupled to the new visual shell.

## Visual constraints

- Use the existing `assets/chrome/xray` frame, field, button, and state
  textures; do not add a second theme system.
- Remove the dashboard-first visual hierarchy from the launcher: no four
  summary metric cards, no generic sidebar headed “РАЗДЕЛЫ”, and no modern
  pill/badge strip competing with the game menu.
- Preserve native window management unless a tested frameless implementation is
  required; visual fidelity applies to the application surface.
- Keep the visual language close to the original trilogy and menu replacers,
  but do not copy personal screenshots, private saves, or unlicensed full game
  archives into Git.
- All labels and counts must be sourced from real discovery/snapshot data;
  missing values stay `—`, `unknown`, or an explicit unsupported state.

## Safety and compatibility

- Discovery is read-only and must not create directories or modify Steam,
  game, save, or Cloud files.
- Import reads a user-selected file and never assumes the matching game is
  installed.
- Editing continues to require the existing immutable plan, source SHA
  freshness, preview, backup/atomic export, CRC/container validation, and
  strict reparse.
- Browser behavior remains local-file-only; desktop discovery is not exposed as
  a fake browser capability.
- Community mods and unverified Enhanced Edition formats remain unsupported or
  read-only according to the existing registry evidence.

## Tests and acceptance

Write behavior tests before implementation for:

1. a synthetic library result containing all four families, including an
   absent S.T.A.L.K.E.R. 2 install with an importable state;
2. manifest-backed, save-directory-only, and completely absent statuses;
3. aggregation of detected saves by content-detected family, with unknown
   candidates not misattributed;
4. manual-path priority and orphan classic install discovery;
5. launcher startup showing all families without opening a save;
6. selecting a discovered row opening the same inspection path as manual file
   import;
7. importing a valid S.T.A.L.K.E.R. 2 fixture without an installed game;
8. malformed/unsupported import preserving the previous snapshot and exposing
   the core error;
9. launcher-to-workbench state and existing edit/preview behavior remaining
   intact.

The relevant targeted tests, `make check`, and the full `make test` suite must
pass. A Linux/offscreen green result proves only local behavior; it does not
prove Windows DPI, packaged startup, Steam Cloud, or in-game loading.

## Non-goals

- implementing new save formats or guessing unsupported fields;
- automatic overwrite or restore of a game slot;
- making Steam Cloud a backend for downloaded local saves;
- creating a second Qt/web UI or replacing the shared editor core;
- accepting community-mod or unverified Enhanced Edition saves as supported.
