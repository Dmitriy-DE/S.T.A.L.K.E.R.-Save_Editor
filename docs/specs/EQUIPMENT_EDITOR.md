# Equipment Editor

## Product contract

The editor exposes one Equipment surface over the shared parser. It presents
weapons, armor and helmets as user-facing categories only for releases with a
separate helmet concept, while preserving the format serializer family as a
separate technical field. An item can be equipped, in the backpack/inventory,
on the belt, or at an unknown placement; an unknown placement is shown as
unknown rather than inferred.

The seven release profiles are independent: SoC Original, SoC Enhanced
Edition, Clear Sky Original, Clear Sky Enhanced Edition, Call of Pripyat
Original, Call of Pripyat Enhanced Edition, and S.T.A.L.K.E.R. 2. No Enhanced
Edition profile inherits an original X-Ray writer without release-specific
format evidence.

## Support maturity

Every equipment operation is described by release-scoped metadata:

- `unsupported`: the UI does not offer the mutation;
- `research`: the UI can show the item and the exact blocker, and the CLI can
  produce reproducible observations;
- `experimental`: source-backed round-trip mutation exists but game loading
  has not been accepted;
- `verified`: the mutation has a release-specific game load/re-save result.

The shared metadata covers durability, upgrades, placement, add, and remove.
Boolean capability fields remain for compatibility with the existing service,
but the Equipment surface uses maturity and reason fields for each operation.

## Equipment behavior

The view supports all/weapon/armor/helmet/equipped/inventory/damaged/staged
filters when those categories exist for the selected release, text search, and
sorting by name, durability, or category. A row shows an icon when an exact
catalog definition supplies one, name, category, location, current durability,
upgrades, and a read-only reason when the field is not safe to edit. Technical
fields remain available in a details tooltip.

Individual repair supports 0–100%, Repair to 100%, and Reset. Bulk repair can
target all damaged items, equipped items, weapons, armor, or helmets. Bulk
operations stage only items with a confirmed writable condition and return a
skipped-item report for everything else. No operation mutates source bytes
before the existing immutable `EditPlan` preview, backup, CRC/SHA, and
read-back pipeline.

## Format boundaries

Original X-Ray profiles reuse the existing condition codec: the authoritative
STATE float, the proven UPDATE quantized mirror, and an optional client mirror
must all pass the current bounds and ambiguity guards. Call of Pripyat Original
helmets are displayed as `helmet` even when their serializer family is `outfit`;
SoC/CS Original do not expose a separate helmet filter. S2 may display a
read-only helmet row only when the save itself provides that category evidence.

S.T.A.L.K.E.R. 2 currently has no accepted durability writer. The product
must expose its equipment projection as read-only/research with a concrete
reason. A writer can become experimental only after controlled same-handle
weapon/armor/helmet samples, A/B game diffs, deterministic anchors, and a
game load/re-save check. A scalar candidate alone is never promoted to a
production writer.

Enhanced Editions remain independent and unavailable/read-only until their
own parser and evidence gates are met.

## Shared front ends and evidence

Qt and web consume the same equipment projection and maturity metadata. Tests
cover category mapping, equipped/backpack placement, CoP helmet taxonomy,
partial/0/50/100 durability, invalid and missing anchors, ambiguous anchors,
no-op bulk repair, skipped unsafe rows, and web/desktop parity. The research
CLI emits hashes, release id, observed item categories, and blocker reasons;
it never writes save bytes.
