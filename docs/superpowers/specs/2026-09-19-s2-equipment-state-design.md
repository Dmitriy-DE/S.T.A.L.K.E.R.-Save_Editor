# S.T.A.L.K.E.R. 2 Equipment State Design

## Problem

The S.T.A.L.K.E.R. 2 editor already has a generic staged durability flow, but
the S2 format adapter disables it and the S2 writer rejects every
EditPlan.durability value. The parser also renders only grid-backed objects,
so an equipped item can be present in the save's owned_handles array without
appearing in the inventory table.

The implementation must improve the real user path without claiming that an
editor round trip is proof that the game accepts an arbitrary save mutation.
The current local corpus has one source-backed S2 equipment state that is safe
to expose: for an actor-owned object with kind=1, a second occurrence of the
same handle at record_offset + 0x23 is followed by a little-endian f32 in
the range 0..1. Across the supplied saves that value changes as the armor
wears and is therefore treated as the S2 armor condition anchor. It is an
experimental writer until a modified copy is loaded and resaved by the game.

## Goals

1. Show confirmed equipped S2 equipment in the inventory table.
2. Read and stage armor condition for the confirmed S2 armor record shape.
3. Apply S2 armor condition in the existing immutable EditPlan transaction,
   rebuild the container, and verify the decoded value after round trip.
4. Remove the false disabled 0% display when a condition is unknown.
5. Keep upgrades, arbitrary weapon condition, and catalog-item giving visibly
   read-only until their save serializers are proven by controlled pairs.
6. Record a repeatable research protocol for the missing controlled pairs.

## Non-goals and safety boundary

- Do not write an offset selected by a heuristic f32 scan.
- Do not treat official .cfg prototype SIDs as save object constructors.
- Do not clone an object, allocate a new handle, or extend the S2 object
  registry without a controlled before -> game action -> after pair.
- Do not write the two observed armor upgrade-key arrays: their meaning
  (available/applicable versus installed/current) and exact boundaries are not
  yet distinguished.
- Do not enable weapon durability merely because a weapon record contains a
  nearby scalar. It needs its own differential evidence.
- Structural CRC/Kraken round trip is necessary, not proof of in-game load.

## Format contract

The new editor.s2_item_state module owns the narrow S2 equipment anchor:

    @dataclass(frozen=True)
    class S2ConditionAnchor:
        handle: int
        record_offset: int
        nested_offset: int
        value_offset: int
        value: float

    def read_s2_armor_condition(
        raw: bytes,
        *,
        handle: int,
        record_offset: int,
        kind_code: int,
    ) -> S2ConditionAnchor | None: ...

    def patch_s2_armor_condition(
        raw: bytearray,
        *,
        handle: int,
        record_offset: int,
        kind_code: int,
        value: float,
    ) -> S2ConditionAnchor: ...

The reader returns None for an unsupported kind or a missing/ambiguous
anchor. The writer rejects non-finite values, values outside 0..1, a handle
whose bytes do not match the supplied record, and an unsupported kind. The
writer changes exactly four bytes at nested_offset + 4.

The parser uses this codec only for kind=1 records. It marks the resulting
InventoryItem.condition as editable and leaves all other S2 equipment
condition values unknown/read-only.

Equipped-item discovery is deliberately narrower than “every owned orphan”:
an owned non-grid record is shown as equipped only when it has an unambiguous
S2 equipment shape (kind 0, 1, or 2 and the same handle at
record_offset + 0x23). Synthetic/orphan records without this shape remain
orphans and cannot accidentally become editable equipment.

## Transaction contract

save_format.patch_save(..., durability={...}) applies condition edits to the
decompressed raw payload alongside money, stack, move, detach, attach, and raw
operations. It must preserve the existing source CRC guard and compact rebuild
logic. After rebuilding it must decode every requested S2 armor condition and
reject the transaction if any requested value differs.

editor.prepare.prepare_edit passes EditPlan.durability to this S2 writer.
The S2 format capability advertises only edit_durability, marked
experimental. add_items, edit_upgrades, and arbitrary S2 weapon condition
remain disabled.

## UI contract

When InventoryItem.condition is None, the condition editor must show an
explicit em dash/unknown state instead of a disabled numeric 0.0. When the
S2 armor anchor is present, the existing percentage spin box and staging
buttons become available and the status text says that the S2 STATE f32
anchor is experimental and a backup is required.

## Verification gates

- Unit tests cover exact offsets, range/error handling, equipped discovery,
  false-zero UI state, writer round trip, stale source rejection, and
  unchanged behavior for stack/money edits.
- A read-only corpus check runs against the local S2 save directory and
  reports how many actor-owned armor records resolve the anchor.
- No test or command writes to the user's Steam Cloud directory.
- In-game acceptance remains an explicit follow-up: duplicate one save, edit
  one armor value, load it in S.T.A.L.K.E.R. 2, save again, and parse the
  result. Only after that gate can the capability be upgraded from
  experimental, and only controlled pairs can unlock weapon/upgrades/add-item
  writers.
