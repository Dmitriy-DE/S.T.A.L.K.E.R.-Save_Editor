# Experimental operations

These operations are intentionally available for testing. They are not marketed as game-safe.

## Move

Patches object record `x/y` and all matching `<handle,x,y>` grid cells. Collision and footprint checks are enforced.

## Detach

- removes every grid cell for the handle;
- writes `0xFFFF` to object record x/y.

Deep mode also removes the handle from the owned-handle array.

Interpretation is intentionally conservative: **detach**, not guaranteed delete.

## Attach orphan

Takes a handle that is already in the owned-handle array but absent from grid, sets record x/y and adds new cells. Width/height are supplied manually.

Potential problem: the orphan may actually be equipped/system data. This is why the feature is gated by the risk checkbox.

## Raw patch

Writes fixed-size scalar bytes into decompressed payload, then rebuilds and round-trips the complete save.

Supported types: `u8`, `u16`, `u32`, `i32`, `f32`, `hex`.

No insertion/deletion is performed by raw patch. `hex` overwrites exactly the supplied number of bytes.

## What to report after an in-game test

For each experiment record:

- source save SHA256;
- handle;
- exact operation;
- whether save appeared in load menu;
- whether it loaded;
- visible result;
- whether re-saving succeeded;
- new cloud/local save for diff.

That evidence should be added to a dated report under `docs/evidence/` rather
than silently changing offsets.
