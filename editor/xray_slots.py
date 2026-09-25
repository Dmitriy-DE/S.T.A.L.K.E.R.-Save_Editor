"""X-Ray inventory slots: names per game and safe placement targets.

Call of Pripyat numbers slots from 1 (``NO_ACTIVE_SLOT`` is 0), confirmed
on the owner's real saves: knife 1, pistol 2, rifle 3, grenade 4,
binoculars 5, bolt 6, outfit 7, PDA 8, detector 9, torch 10, artefact 11,
helmet 12.  Shadow of Chornobyl and Clear Sky number the same slots from 0,
as their configs (``slot = 0`` for the knife) and engines do.

A target is offered only when the game itself would put the item there: the
backpack, the belt for artefacts, and the item's own base slot — which the
game writes into the save.  Anything else could leave the save in a state
the game never produces (bread in the helmet slot).
"""

from __future__ import annotations

from .i18n import tr

_SLOT_ORDER = (
    "Нож",
    "Пистолет",
    "Основное оружие",
    "Граната",
    "Бинокль",
    "Болт",
    "Броня",
    "КПК",
    "Детектор",
    "Фонарь",
    "Артефакт",
    "Шлем",
)
COP_SLOT_NAMES: dict[int, str] = {index + 1: name for index, name in enumerate(_SLOT_ORDER)}
# No helmet slot before Call of Pripyat.
EARLY_SLOT_NAMES: dict[int, str] = {index: name for index, name in enumerate(_SLOT_ORDER[:-1])}


def slot_names(release_id: str | None) -> dict[int, str]:
    value = str(release_id or "").casefold()
    return COP_SLOT_NAMES if "cop" in value or not value else EARLY_SLOT_NAMES


def slot_label(slot: int | None, release_id: str | None = None) -> str:
    if slot is None:
        return tr("Слот")
    name = slot_names(release_id).get(int(slot))
    return tr("Слот: {0}", tr(name)) if name else tr("Слот {0}", slot)


def placement_label(placement_type: str | None, slot: int | None, release_id: str | None = None) -> str:
    if placement_type == "slot":
        return slot_label(slot, release_id)
    return {"belt": tr("Пояс"), "ruck": tr("Рюкзак")}.get(str(placement_type), tr("Неизвестно"))


def is_artefact_section(section: str | None) -> bool:
    return str(section or "").casefold().startswith("af_")


def placement_targets(
    section: str | None,
    base_slot: int | None,
    release_id: str | None = None,
) -> tuple[tuple[str, int | None], ...]:
    """The places the game itself would use for this item."""

    targets: list[tuple[str, int | None]] = [("ruck", None)]
    if is_artefact_section(section):
        targets.append(("belt", None))
    if base_slot is not None and int(base_slot) in slot_names(release_id):
        targets.append(("slot", int(base_slot)))
    return tuple(targets)


def placement_allowed(
    placement_type: str,
    slot: int | None,
    *,
    section: str | None,
    base_slot: int | None,
    release_id: str | None = None,
) -> bool:
    return (placement_type, slot if placement_type == "slot" else None) in placement_targets(
        section, base_slot, release_id
    )


__all__ = [
    "COP_SLOT_NAMES",
    "EARLY_SLOT_NAMES",
    "is_artefact_section",
    "placement_allowed",
    "placement_label",
    "placement_targets",
    "slot_label",
    "slot_names",
]
