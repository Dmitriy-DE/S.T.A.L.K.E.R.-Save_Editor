# Equipment Editor evidence — 2026-09-19

## Implemented surface

The shared projection in `editor/equipment.py` separates the product category
(`weapon`, `armor`, `helmet`, `module`, `device`, `consumable`, `ammo`,
`artifact`, `quest`, `other`) from the serializer family and exposes
`equipped`, `inventory`, `belt`, or `unknown` placement. Exact catalog definitions
provide names and icon coordinates; an absent definition never creates a
fabricated name or icon.

Qt and web consume the same projection contract. Qt has a dedicated Equipment
surface with release-scoped category/location/damaged/staged filters, search,
sorting, individual 0–100% staging, reset, and bulk repair actions. Bulk staging uses
the immutable `EditPlan.durability` path and reports every skipped item.

## Release maturity

| Profile | Durability | Upgrades | Placement/add/remove |
|---|---|---|---|
| SoC Original | experimental X-Ray condition anchors | unsupported | experimental structural gates |
| Clear Sky Original | experimental X-Ray condition anchors | experimental structural gate | experimental structural gates |
| Call of Pripyat Original | experimental X-Ray condition anchors | experimental structural gate | experimental structural gates |
| S.T.A.L.K.E.R. 2 | experimental for source-backed weapon/armor anchors; game acceptance pending | research/read-only | unsupported |
| SoC Enhanced Edition | unsupported | unsupported | unsupported |
| Clear Sky Enhanced Edition | unsupported | unsupported | unsupported |
| Call of Pripyat Enhanced Edition | unsupported | unsupported | unsupported |

`experimental` means the exact parser/writer round-trip is guarded, not that
the game accepted the edited file. `verified` is intentionally unused until a
release-specific load/re-save result exists.

Only Call of Pripyat Original and S2 expose a separate helmet category in the
current product model. SoC/CS Original treat helmet-like outfit keys as armor;
Enhanced Edition filters remain unavailable with their independent unsupported
profiles.

## S.T.A.L.K.E.R. 2 research and writer boundary

`tools/research_equipment.py` accepts explicit save paths, records each source
SHA-256, release id, observed categories/locations, condition rows, and
concrete blockers. It does not write save bytes. At least three controlled
same-handle weapon/armor/helmet states plus A/B game diffs and game
load/re-save evidence is still required before the narrow S2 armor durability
writer can be promoted beyond `experimental`; devices, modules, unresolved
rows and unproven upgrade vectors remain read-only.

Example:

```bash
python3 tools/research_equipment.py --json \
  /path/to/sample-a.sav /path/to/sample-b.sav /path/to/sample-c.sav
```

The report is observational. A scalar candidate, catalog prototype SID, or
structural binary round-trip does not broaden S2 writing beyond the exact
source-backed weapon/armor anchors.

## Verification

The local implementation gate for this change is:

```text
pytest tests/test_equipment.py tests/test_equipment_edits.py tests/test_equipment_research.py tests/test_ui_equipment.py
```

The tests cover category/family separation, CoP helmet taxonomy, equipped and
backpack rows, 0/50/100 values, invalid/missing/ambiguous safety boundaries,
no-op and bulk skip reports, S2 research gating, and Qt signal/staging parity.
