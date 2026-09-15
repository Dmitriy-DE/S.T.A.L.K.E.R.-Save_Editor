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


__all__ = ["FormatCapabilities"]
