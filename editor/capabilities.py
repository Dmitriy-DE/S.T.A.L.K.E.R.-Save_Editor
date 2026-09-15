"""Immutable capability declarations shared by every editor front end."""

from __future__ import annotations

from dataclasses import dataclass, replace

# This set is intentionally empty until M10 has a documented, per-release
# game load + in-game re-save result.  Synthetic parser round-trips and a
# different game's result must never open a mutation capability here.
_GAMEPLAY_VERIFIED_RELEASES: frozenset[str] = frozenset()


@dataclass(frozen=True)
class FormatCapabilities:
    """Describe edits a format has proved safe to expose to users."""

    read_inventory: bool = False
    edit_money: bool = False
    edit_stacks: bool = False
    move_items: bool = False
    add_items: bool = False
    remove_items: bool = False
    edit_durability: bool = False
    edit_upgrades: bool = False
    catalog: bool = False

    def as_dict(self) -> dict[str, bool]:
        """Return the stable JSON-shaped projection shared by Qt and web."""

        return {
            "read_inventory": self.read_inventory,
            "edit_money": self.edit_money,
            "edit_stacks": self.edit_stacks,
            "move_items": self.move_items,
            "add_items": self.add_items,
            "remove_items": self.remove_items,
            "edit_durability": self.edit_durability,
            "edit_upgrades": self.edit_upgrades,
            "catalog": self.catalog,
        }


def gameplay_verified_release_ids() -> frozenset[str]:
    """Return releases with an accepted M10 load/re-save result."""

    return _GAMEPLAY_VERIFIED_RELEASES


def gate_mutations_for_release(
    release_id: str,
    capabilities: FormatCapabilities,
) -> FormatCapabilities:
    """Keep unverified release mutations read-only.

    The parser can still be used by the M10 preparation tool through the
    format writer.  This gate controls user-facing capability metadata only,
    so a local synthetic test cannot be mistaken for game evidence.
    """

    if release_id in _GAMEPLAY_VERIFIED_RELEASES:
        return capabilities
    return replace(
        capabilities,
        edit_money=False,
        edit_stacks=False,
        move_items=False,
        add_items=False,
        remove_items=False,
        edit_durability=False,
        edit_upgrades=False,
    )


__all__ = [
    "FormatCapabilities",
    "gameplay_verified_release_ids",
    "gate_mutations_for_release",
]
