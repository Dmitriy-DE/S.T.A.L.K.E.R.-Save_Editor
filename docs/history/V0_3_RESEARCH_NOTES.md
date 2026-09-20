# Research notes — v0.3 experimental

## Summary

We still have not found a mature public universal offline STALKER 2 save editor that safely edits arbitrary inventory objects and rebuilds the same save. Public tools mostly fall into these groups:

1. **Console/item spawners** — let the running game create valid objects using `XCreateItemInInventoryByID`.
2. **Specialized offline patchers/repair tools** — modify a narrow, known structure and fail closed otherwise.
3. **Cloud/sync helpers** — move valid save files between storage backends.

This project follows the specialized offline patcher model for confirmed fields, and now includes a separately gated structural/raw research lab.

## Similar solutions studied

- SteamCloudFileManager — direct Steam RemoteStorage management; used as a separate helper.
  https://github.com/Fldicoahkiin/SteamCloudFileManager
- Fire Save Repair — STALKER 2 offline repair tool with backup/CRC/unsupported-structure blocking.
  https://www.nexusmods.com/stalker2heartofchornobyl/mods/2601
- Stalker2Control — UETools frontend with item categories/SIDs and money/item commands.
  https://github.com/Rianvy/Stalker2Control
- Console command list / item-spawn syntax.
  https://github.com/scalespeeder/stalker-2-pc-console-common-useful-commands-list
- GamerGuides item DB / public item IDs.
  https://www.gamerguides.com/stalker-2-heart-of-chornobyl/database/
- Game8 human-facing wiki.
  https://game8.co/games/STALKER-2-Heart-of-Chornobyl
- Official Zone Kit Phase 2 / Save & Load modding support.
  https://www.stalker2.com/news/zone-kit-phase-2-new-features
  https://zonekit-support.stalker2.com/

## Confirmed from the user's saves

Known money values:

```text
217BB29D... = 48645
D9338CF2... = 58870
D639C0F2... = 56995
```

The D639 save yielded:

```text
owned handles = 53
grid cells = 65
visible parsed inventory objects = 34
owned handles without grid cells = 14
```

The previous hard-coded grid offset was replaced by count-derived parsing:

```text
money
u32 flag
u16 owned_count
u32 owned_handles[owned_count]
u16 grid_count
<IHH> grid_cells[grid_count]
```

Object record x/y at `+11/+13` was confirmed against grid positions. This enabled experimental variable-length grid/owned-array rebuild.

## v0.3 experimental operations

- move: patch object x/y + all grid cells;
- detach: remove grid cells + set record x/y to FFFF;
- deep detach: additionally remove handle from owned list;
- attach orphan: add cells for an already-owned handle missing from the grid;
- raw scalar/hex patches;
- object record dump/diff.

All of these pass CRC + Kraken + parser round-trip tests. Only in-game testing can establish semantic correctness.

## Why arbitrary Add Item is still not labeled as working

The public SID is known for many objects, but the offline-save representation is not yet confirmed. A correct new item needs at least:

- a new/valid handle;
- object registry insertion and its count/index updates;
- prototype/SID reference;
- inventory owner/container references;
- grid cells;
- extra components for weapons/armor/quest items;
- allocator/identity state if the engine tracks one.

`type-key` (`record +8..+10`) is exposed for research because it is stable across nearby saves, but it is not yet proven to be a SID hash/index.

## Best next experiment

On a local install where UETools can run:

1. Save A.
2. Spawn exactly one known SID, e.g. `Bandage` or `GunAK74_ST`.
3. Save B immediately.
4. Compare owned handles, grid cells, object records and surrounding registry bytes.
5. Repeat with 3+ different SIDs.

That should reveal the minimal object-allocation path required for a genuine `Add by SID` implementation.
