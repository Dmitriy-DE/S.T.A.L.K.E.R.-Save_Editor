"""Immutable capability declarations shared by every editor front end."""

from __future__ import annotations

from dataclasses import dataclass, replace

# The owner accepted the three installed original X-Ray releases after loading
# the edited copies in each official game and confirming the visible result.
# S.T.A.L.K.E.R. 2 and Enhanced Editions remain gated until their own local
# samples exist.  The evidence document records that the owner did not retain
# a parser read-back hash from a second in-game save; this set is therefore an
# explicit product acceptance for the installed originals, not a claim that
# every unobserved release or serializer family is interchangeable.
_GAMEPLAY_VERIFIED_RELEASES: frozenset[str] = frozenset(
    {"stalker-soc", "stalker-cs", "stalker-cop"}
)
_MUTATION_CAPABILITY_FIELDS: frozenset[str] = frozenset(
    {
        "edit_money",
        "edit_stacks",
        "move_items",
        "add_items",
        "remove_items",
        "edit_durability",
        "edit_upgrades",
        "edit_relations",
        "edit_player_faction",
    }
)


@dataclass(frozen=True)
class FormatCapabilities:
    """Describe edits a format may expose to users.

    ``experimental_fields`` keeps source-backed, round-trip-tested edits
    visibly distinct from fields accepted by a controlled in-game check.
    """

    read_inventory: bool = False
    edit_money: bool = False
    edit_stacks: bool = False
    move_items: bool = False
    add_items: bool = False
    remove_items: bool = False
    edit_durability: bool = False
    edit_upgrades: bool = False
    catalog: bool = False
    edit_relations: bool = False
    edit_player_faction: bool = False
    experimental_fields: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        fields = frozenset(self.experimental_fields)
        unknown = fields - _MUTATION_CAPABILITY_FIELDS
        if unknown:
            names = ", ".join(sorted(str(value) for value in unknown))
            raise ValueError(f"unknown capability in experimental_fields: {names}")
        inactive = {field for field in fields if not bool(getattr(self, field))}
        if inactive:
            names = ", ".join(sorted(inactive))
            raise ValueError(
                f"experimental capability must be enabled first: {names}"
            )
        object.__setattr__(self, "experimental_fields", fields)

    def is_experimental(self, field: str) -> bool:
        """Return whether one enabled edit needs an explicit UI warning."""

        return field in self.experimental_fields

    def as_dict(self) -> dict[str, object]:
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
            "edit_relations": self.edit_relations,
            "edit_player_faction": self.edit_player_faction,
            "experimental_fields": sorted(self.experimental_fields),
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
        edit_relations=False,
        edit_player_faction=False,
        experimental_fields=frozenset(),
    )


__all__ = [
    "FormatCapabilities",
    "gameplay_verified_release_ids",
    "gate_mutations_for_release",
]
