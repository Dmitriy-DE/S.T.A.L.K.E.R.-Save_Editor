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
unsupported or failed row stays read-only with its reason. A screenshot of a
loaded save is recorded as an intermediate `pending-owner-resave` result; it
does not substitute for parsing the file written back by the game.

## Current evidence matrix

| Release | Game/build | Source SHA-256 | Edited SHA-256 | Re-saved SHA-256 | Visible result | Parser result | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `stalker2` | not run | — | — | — | — | — | `pending-owner-run` |
| `stalker-soc` | local Steam original; build not recorded | `832e50d33626fb879f04a0507bf759ead5c888b508bb64b5a2176ae69e880101` | `f8c958e511f21fff3459220ff6794e086f00dde463a24005b0baceed8a4d1c2b` | — | Loaded in official game; money `123456789`; inventory visible | Prepared output parses as `stalker-soc`; game re-save not read back | `pending-owner-resave` |
| `stalker-cs` | local Steam original; build not recorded | `e8d86714448846d91c027ea706602bee30dc456cc66192d418f91990a2faeee0` | `c91234bf1920d67e438fd45d28716b0255e8d46cd70b5a49e5ff2c22aa2af9e2` | — | Loaded in official game; money `123456789`; inventory visible | Prepared output parses as `stalker-cs`; game re-save not read back | `pending-owner-resave` |
| `stalker-cop` | local Steam original; build not recorded | `79be7cc6bf058330536d58c8b4ddbee6fb7268b940f13321a6dfc23a85b4cb75` | `ab30ad79960585f534f8be1b11278b0a4a06e641ddbfc2f30f567d6f15cb308d` | — | Loaded in official game; money `123456789`; inventory visible; ammo stack `x30` visible | Prepared output parses as `stalker-cop`; game re-save not read back | `pending-owner-resave` |
| `stalker-soc-ee` | no accepted local sample | — | — | — | unavailable | unavailable | `pending-owner-run` |
| `stalker-cs-ee` | no accepted local sample | — | — | — | unavailable | unavailable | `pending-owner-run` |
| `stalker-cop-ee` | no accepted local sample | — | — | — | unavailable | unavailable | `pending-owner-run` |

Enhanced Edition rows are separate on purpose. Original X-Ray bytes must never
be routed through an Enhanced profile, and one Enhanced release cannot prove
the other two.

The owner supplied visual load evidence from three local screenshots. The
screenshots themselves remain outside Git; only their SHA-256 values are
recorded here:

| Release | Screenshot SHA-256 |
| --- | --- |
| `stalker-cs` | `12e8b7fc317034542853b33db11512393ad3db703abccd00ee2ef220e21d04e6` |
| `stalker-soc` | `216b074800008fd0941191133e484379ea739cdf404fe43430af64cbd986eaf5` |
| `stalker-cop` | `f882a7af65a42af615092442dcd67b603ea4b3d5fdf15187aa23aad61336800d` |

## Local automated preparation checks

- `PYTHON=.venv/bin/python -m pytest tests/test_ingame_protocol.py -q` — exit 0,
  `5 passed`.
- No real game was launched and no game directory was written by this check.
