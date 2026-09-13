# Prompt for Codex

Continue developing this repository as an experimental but fail-closed offline/cloud save editor for **S.T.A.L.K.E.R. 2: Heart of Chornobyl** on Linux.

Read, in order:

1. `README.md`
2. `docs/SAVE_FORMAT.md`
3. `docs/CODEX_HANDOFF.md`
4. `docs/EXPERIMENTAL.md`
5. `NOTES_FROM_RESEARCH.md`
6. `save_format.py`
7. `app.py`
8. `steam_cloud.py`

Do not remove existing safety gates: backup, CRC, decompression round-trip, stale SHA256 protection, `persisted=true`, cloud read-back verification.

Current safe/confirmed features:

- money read/write;
- inventory grid parser;
- stack count + cached weight;
- Steam Cloud read/write through SteamCloudFileManager worker.

Current experimental features:

- move item;
- detach / deep detach;
- attach existing orphan handle;
- raw scalar/hex patches;
- object record dump/diff.

Highest-priority goals:

1. reverse-engineer prototype/SID mapping from object records using controlled save diffs and public Zone Kit/config data;
2. locate full object registry boundaries/count/allocator state;
3. implement true `Add item by SID` with a newly allocated handle and all required references;
4. implement true clone and delete with reference cleanup;
5. identify and validate durability on at least three controlled states before exposing it as safe;
6. map SIDs to human names using public item catalogs/configs;
7. compact rebuild: preserve original Kraken-compressed blocks and replace only modified blocks when possible;
8. add regression tests for every newly promoted field/operation.

Engineering rule: if a structure is ambiguous, stop instead of guessing. Experimental functionality may exist behind an explicit risk gate, but must be labelled as experimental and always create a backup.
