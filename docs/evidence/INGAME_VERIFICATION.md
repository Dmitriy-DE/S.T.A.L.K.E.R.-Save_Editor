# In-game verification protocol — M10

This document records game load/re-save evidence only. It stores hashes and
results, never save bytes. A parser round-trip, a matching extension, or a
successful result from another game is not an in-game pass.

## Procedure

For each row below, use a fresh workspace and one ordinary official save from
the selected release:

1. Close the game and make sure the selected save is not being synchronized or
   rewritten by another process.
2. Prepare a copy and change only money. The command does not write the source
   file or a game directory:

   ```bash
   python -m tools.prepare_ingame_verification \
     --release <release-id> \
     --source /absolute/path/to/save \
     --workspace /absolute/path/to/private/m10/<release-id> \
     --money <new-value>
   ```

3. Copy the generated `edited_path` to a disposable slot/location accepted by
   that release. Do not overwrite the original save.
4. Launch the matching official game manually, load the edited copy, and
   confirm that the money value is the requested value and that the visible
   world/inventory has no unexpected change.
5. Save again from inside the game. Keep that re-saved file outside the Git
   worktree.
6. Parse the game re-save and record the command output:

   ```bash
   python -m tools.verify_ingame_result \
     --manifest /absolute/path/to/private/m10/<release-id>/manifest.json \
     --resaved /absolute/path/to/private/m10/<release-id>/resaved-save
   ```

7. Add only release version/build, source/edited/re-saved SHA-256, observed
   value, visible result, parser result, and a concise limitation to the row.

The first successful row enables only `edit_money` for that exact release.
Later cards repeat the same load/re-save gate for their own capability. An
unsupported or failed row stays read-only with its reason.

## Current evidence matrix

| Release | Game/build | Source SHA-256 | Edited SHA-256 | Re-saved SHA-256 | Visible result | Parser result | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `stalker2` | not run | — | — | — | — | — | `pending-owner-run` |
| `stalker-soc` | not run | — | — | — | — | — | `pending-owner-run` |
| `stalker-cs` | not run | — | — | — | — | — | `pending-owner-run` |
| `stalker-cop` | not run | — | — | — | — | — | `pending-owner-run` |
| `stalker-soc-ee` | no accepted local sample | — | — | — | unavailable | unavailable | `pending-owner-run` |
| `stalker-cs-ee` | no accepted local sample | — | — | — | unavailable | unavailable | `pending-owner-run` |
| `stalker-cop-ee` | no accepted local sample | — | — | — | unavailable | unavailable | `pending-owner-run` |

Enhanced Edition rows are separate on purpose. Original X-Ray bytes must never
be routed through an Enhanced profile, and one Enhanced release cannot prove
the other two.

## Local automated preparation checks

- `PYTHON=.venv/bin/python -m pytest tests/test_ingame_protocol.py -q` — exit 0,
  `5 passed`.
- No real game was launched and no game directory was written by this check.
