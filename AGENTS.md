# Working on S.T.A.L.K.E.R. Save Editor

## Start here

Read `README.md`, `docs/STATUS.md` and the relevant format/evidence document before changing parser or writer behaviour.

Keep each change bounded. Prefer one user-facing problem per branch/PR.

## Safety rules

- Never commit personal save files, credentials, Steam session material or user-specific paths.
- Do not enable a write capability from a guessed offset, SID, record boundary or serializer shape.
- Unknown or ambiguous fields stay read-only.
- Preserve CRC / framing / round-trip / backup / fresh-SHA checks.
- Local export must not silently destroy the original save.
- Steam Cloud writes must remain explicit; an uncertain write must never be retried automatically.
- Synthetic round-trip tests do not count as proof that the game accepts a mutation.
- Keep live game / Steam tests separate from CI unless the test is explicitly designed and authorised for that environment.

## Architecture rules

- UI surfaces use the shared editor service; do not duplicate mutation logic in Qt, web or CLI.
- Keep release capabilities explicit and format-specific.
- Content-based detection takes precedence over filename/path assumptions.
- New parser/writer behaviour needs positive and negative regression tests.
- Web and desktop capability reporting should stay consistent.

## Before finishing

- Use the [L1–L5 verification levels](docs/roadmap/RL-reliability.md) in PR reports.
- run the smallest relevant tests first, then the broader project checks;
- document any unverified game/platform/cloud assumptions;
- update public docs only when behaviour actually changed;
- link the issue/PR that explains the user-facing change.
