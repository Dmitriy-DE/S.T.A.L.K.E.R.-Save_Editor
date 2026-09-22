# S.T.A.L.K.E.R. 2 equipment corpus report — 2026-09-22

This evidence is aggregate-only. The repository contains no personal save
paths, raw payload bytes, or copied save files. The corpus command assigns
accepted inputs anonymous `sample-001`-style identifiers and records only
SHA-256, packed/raw sizes, parser release, category totals, ownership/grid/
equipped counts, and condition-anchor status.

## Reproducible read-only command

```bash
python3 tools/research_equipment.py \
  --input-root /explicit/copied/S2/SaveGames/Data \
  --report /tmp/s2-equipment-corpus.json \
  --release stalker2
```

Every candidate is snapshotted before parsing. After each input, the command
compares bytes, size, and `mtime_ns`; a changed input aborts the run instead
of producing evidence for a moving corpus. Files that the parser cannot
accept are counted only in `rejected_count`; their names and paths are not
written to the report.

## Observed boundary

The current read-only scan of the supplied local corpus accepted 6 S2 Data
files and rejected 9 files without a unique wallet/parser boundary. The
accepted files contain 228 actor-owned observations, 171 grid observations
and 54 equipped observations in aggregate; category totals are 14 weapons,
16 armor, 2 helmets, 17 module observations, 4 devices and 116 unresolved or
other rows. S2 armour perk rows such as `*_Armor_protection*` are classified
as modules even when their opaque serialized kind resembles a weapon. Accepted
files are approximately 6.65–6.73 MB packed and
26.07–26.69 MB raw. The command recorded each accepted input SHA-256 and
verified bytes, size and `mtime_ns` before/after parsing.

Separate equipment evidence records armor condition anchors, source-backed
weapon condition candidates, device rows and module observations. The current
codec enables only the confirmed weapon/armor condition shapes as
`experimental`; this corpus alone does not make them game-accepted.

`NVG_NPC_Gen3` is an actor/grid device observation. `Binoculars_*` and
`NVG_Gen2` appearing solely in the embedded name table are metadata, not owned
inventory rows. The synthetic regression test enforces that boundary.

## Gate

This report is research evidence only. It does not promote an experimental
writer to game-verified and never turns an unknown condition into zero.
