"""Immutable capability declarations shared by every editor front end."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from .capability_types import CapabilityMaturity, CapabilitySupport
from .equipment import EquipmentSupport

# The owner accepted the three installed original X-Ray releases after loading
# the edited copies in each official game and confirming the visible result.
# S.T.A.L.K.E.R. 2 and Enhanced Editions remain gated for game acceptance.
# Source-backed S2 condition edits may be exposed as experimental, while
# Enhanced Editions stay read-only until their own samples exist. This set is
# evidence ownership, not a second app/release registry: app IDs and paths
# stay in editor.releases.
_GAMEPLAY_VERIFIED_RELEASES: frozenset[str] = frozenset(
    {"stalker-soc", "stalker-cs", "stalker-cop"}
)
_MUTATION_CAPABILITY_FIELDS = (
    "edit_money",
    "edit_stacks",
    "move_items",
    "add_items",
    "remove_items",
    "edit_durability",
    "edit_upgrades",
    "edit_relations",
    "edit_player_faction",
    "edit_placement",
)
_UNSUPPORTED = CapabilitySupport("unsupported")


@dataclass(frozen=True)
class FormatCapabilities:
    """Describe format edits through one maturity model.

    The ``edit_*`` attributes are compatibility projections.  They are not
    stored state and can never disagree with ``mutation_support``: only
    ``experimental`` and ``verified`` maturity is writable.
    """

    read_inventory: bool = False
    catalog: bool = False
    equipment: EquipmentSupport | None = None
    mutation_support: Mapping[str, CapabilitySupport] = field(default_factory=dict)

    def __post_init__(self) -> None:
        raw = dict(self.mutation_support)
        unknown = set(raw) - set(_MUTATION_CAPABILITY_FIELDS)
        if unknown:
            names = ", ".join(sorted(str(value) for value in unknown))
            raise ValueError(f"unknown capability in mutation_support: {names}")
        for field_name, support in raw.items():
            if not isinstance(support, CapabilitySupport):
                raise TypeError(
                    f"mutation_support[{field_name!r}] must be CapabilitySupport"
                )
        normalized = {
            field_name: raw.get(field_name, _UNSUPPORTED)
            for field_name in _MUTATION_CAPABILITY_FIELDS
        }
        object.__setattr__(self, "mutation_support", MappingProxyType(normalized))

    def support(self, field_name: str) -> CapabilitySupport:
        """Return one mutation maturity or reject a misspelled field."""

        if field_name not in _MUTATION_CAPABILITY_FIELDS:
            raise KeyError(f"unknown mutation capability: {field_name!r}")
        return self.mutation_support[field_name]

    @property
    def experimental_fields(self) -> frozenset[str]:
        """Return experimental fields as a computed compatibility projection."""

        return frozenset(
            field_name
            for field_name in _MUTATION_CAPABILITY_FIELDS
            if self.support(field_name).maturity == "experimental"
        )

    def is_experimental(self, field_name: str) -> bool:
        """Return whether one enabled edit needs an explicit UI warning."""

        return self.support(field_name).maturity == "experimental"

    @property
    def edit_money(self) -> bool:
        return self.support("edit_money").writable

    @property
    def edit_stacks(self) -> bool:
        return self.support("edit_stacks").writable

    @property
    def move_items(self) -> bool:
        return self.support("move_items").writable

    @property
    def add_items(self) -> bool:
        return self.support("add_items").writable

    @property
    def remove_items(self) -> bool:
        return self.support("remove_items").writable

    @property
    def edit_durability(self) -> bool:
        return self.support("edit_durability").writable

    @property
    def edit_upgrades(self) -> bool:
        return self.support("edit_upgrades").writable

    @property
    def edit_relations(self) -> bool:
        return self.support("edit_relations").writable

    @property
    def edit_player_faction(self) -> bool:
        return self.support("edit_player_faction").writable

    @property
    def edit_placement(self) -> bool:
        return self.support("edit_placement").writable

    def as_dict(self) -> dict[str, object]:
        """Return the canonical JSON projection shared by Qt, web and CLI."""

        payload: dict[str, object] = {
            "read_inventory": self.read_inventory,
            "catalog": self.catalog,
            "equipment": self.equipment.as_dict() if self.equipment is not None else None,
            "mutation_support": {
                field_name: self.support(field_name).as_dict()
                for field_name in _MUTATION_CAPABILITY_FIELDS
            },
            # Keep the established web/UI contract while deriving every bool.
            "experimental_fields": sorted(self.experimental_fields),
        }
        payload.update(
            {
                field_name: getattr(self, field_name)
                for field_name in _MUTATION_CAPABILITY_FIELDS
            }
        )
        return payload


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
    downgraded: dict[str, CapabilitySupport] = {}
    for field_name in _MUTATION_CAPABILITY_FIELDS:
        support = capabilities.support(field_name)
        if support.maturity == "verified":
            downgraded[field_name] = CapabilitySupport(
                "research",
                support.reason
                or "game load/re-save evidence is not accepted for this release",
            )
        else:
            downgraded[field_name] = support
    return replace(capabilities, mutation_support=downgraded)


__all__ = [
    "CapabilityMaturity",
    "CapabilitySupport",
    "FormatCapabilities",
    "gameplay_verified_release_ids",
    "gate_mutations_for_release",
]
