# SAVE_FORMAT.md — confirmed facts vs hypotheses

## Confirmed

Container:

```text
u32 LE unpacked_size
Kraken/Oodle stream
u32 LE CRC32(file_without_final_crc)
```

Unique campaign/player anchor used by this build:

```python
MONEY_ANCHOR = bytes.fromhex(
  "0038010000000110cacfa848c8952149b51b9444000000000600000000060000"
)
```

Immediately after anchor:

```text
u32 money
u32 owned_flag
u16 owned_handle_count
u32 owned_handles[owned_handle_count]
u16 grid_cell_count
GridCell[grid_cell_count]
```

GridCell = `<IHH>` = handle,x,y.

Object records confirmed for inventory objects:

```text
+0  u32 handle
+11 u16 x
+13 u16 y
+18 u8 0x38
+19 u32 count
+24 f32 total_weight
+31 u8 kind
```

## Useful observed invariant

For the same object handle across nearby saves, the bytes at `+8..+10` are stable. v0.3 exposes them as `type-key`, but does NOT claim they are the public SID/hash.

## Structural array editing implemented

Because owned/grid arrays are count-prefixed and contiguous, v0.3 can rebuild those arrays with changed lengths while leaving the rest of raw payload intact. This is how experimental detach/attach is implemented.

## Not confirmed

- root object registry count / full object record boundaries;
- handle allocator state;
- prototype SID reference/hash;
- durability;
- attachment lists;
- upgrade state;
- deletion semantics / garbage collection;
- whether all `owned_handles` are inventory ownership or include equipment/system references.

## Reverse-engineering strategy

Use controlled pairs and `cli.py diff-record`:

```bash
python3 cli.py diff-record A.sav B.sav 0xHANDLE --limit 4096
```

Best experiments:

- same weapon before/after exactly one durability change;
- same item moved one grid cell;
- same stack after +1 item;
- item equipped vs unequipped;
- attach/detach via normal game mechanics if possible;
- add a known SID through console on local Windows install, then diff the resulting save.
