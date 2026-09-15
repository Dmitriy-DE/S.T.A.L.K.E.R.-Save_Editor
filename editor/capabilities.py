"""Immutable capability declarations shared by every editor front end."""

from __future__ import annotations

from dataclasses import dataclass


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


__all__ = ["FormatCapabilities"]
