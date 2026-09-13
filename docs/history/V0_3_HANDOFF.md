# CODEX HANDOFF

You are continuing an experimental Linux offline/cloud save editor for **S.T.A.L.K.E.R. 2: Heart of Chornobyl (Steam App ID 1643320)**.

## Goal

Make one app capable of:

```text
Steam Cloud -> backup -> parse -> edit money/inventory -> verify -> upload -> persisted/read-back verify
```

Eventually support:

- human item names;
- add by SID;
- remove;
- clone;
- durability;
- attachments/upgrades.

## Do not regress

`save_format.py` safe paths already work on real user saves:

- CRC validation;
- Kraken decompression;
- money detection/edit;
- inventory grid parser;
- stack count + cached-weight edit;
- deterministic uncompressed-block rebuild;
- round-trip validation.

`steam_cloud.py` uses SteamCloudFileManager `--steam-worker`; keep stale SHA guard + backup + persisted + read-back validation.

## Real validation data (not bundled)

Known adjacent saves from the same campaign:

```text
217BB29D4FA4C87BD9F734AE755338CB.sav  -> UI money 48645
D9338CF24B87162D6472C79DF9E1CFFE.sav  -> parsed money 58870
D639C0F24C64FC164326E8967A8DCCBE.sav  -> UI money 56995
```

The D639 save parsed as:

```text
owned handles: 53
grid cells:    65
visible objects parsed: 34
owned-without-grid candidates: 14
```

Examples confirmed from UI count:

```text
0x300027C8 count 34
0x30002665 count 211
... plus 10,21,3,2,6,20,60,60,62,25 etc.
```

## v0.3 new structural discovery

The old `grid = money_anchor + 0x100` rule was replaced with count-derived parsing:

```text
money +4 bytes -> owned_flag u32
then u16 owned_count
then owned_count * u32 handles
then u16 grid_count
then grid_count * <IHH> cells
```

This is much stronger and allows variable-length rebuild of those two arrays.

Object record position is also confirmed:

```text
+11 u16 x
+13 u16 y
```

That enabled move/detach/attach-orphan experiments.

## Highest-value next task: SID/prototype mapping

Public console item IDs exist (`Bandage`, `A545D`, `GunAK74_ST`, etc.), but we do not yet know their offline-save representation.

Suggested attack:

1. obtain two local-game saves differing only by one spawned known SID;
2. compare new handle(s) in owned list/grid;
3. extract full new object record and dependent references;
4. compare multiple SIDs across same category;
5. search Zone Kit/config dumps for any numeric/index representation matching bytes around record `+8..+17`;
6. only after confirming the registry/count/allocator implement `new object`.

Do NOT assume `type-key = raw[+8:+11]` is the SID hash. It is merely stable observed data.

## Durability strategy

Use the same handle before/after controlled damage/repair:

```bash
python3 cli.py diff-record before.sav after.sav HANDLE --limit 4096
```

Filter changed groups by plausible `f32 0..1` / `u8 0..100`, but confirm on at least 3 values before naming an offset `durability`.

## Existing public projects/sources

- SteamCloudFileManager: https://github.com/Fldicoahkiin/SteamCloudFileManager
- Fire Save Repair: https://www.nexusmods.com/stalker2heartofchornobyl/mods/2601
- Stalker2Control: https://github.com/Rianvy/Stalker2Control
- console command list: https://github.com/scalespeeder/stalker-2-pc-console-common-useful-commands-list
- GamerGuides DB: https://www.gamerguides.com/stalker-2-heart-of-chornobyl/database/
- Game8: https://game8.co/games/STALKER-2-Heart-of-Chornobyl
- official Zone Kit Phase 2: https://www.stalker2.com/news/zone-kit-phase-2-new-features
- Zone Kit docs: https://zonekit-support.stalker2.com/

## Preferred engineering rules

- fail closed on ambiguous signatures;
- backups before mutation;
- never upload if analyzed SHA != fresh SHA;
- never upload if CRC/round-trip fails;
- experimental operations remain separately gated;
- record every newly confirmed offset and exact evidence in docs;
- write a regression test before promoting an experimental field to safe.

## Useful commands

```bash
make check
make selftest SAVE=/path/to/real.sav
python3 cli.py info save.sav
python3 cli.py inventory save.sav --all
python3 cli.py orphans save.sav
python3 cli.py dump-record save.sav HANDLE --limit 4096
python3 cli.py diff-record A.sav B.sav HANDLE --limit 4096
```
