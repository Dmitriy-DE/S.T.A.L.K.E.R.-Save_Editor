"""Read-only comparison of two inspected saves (money, items, actor facts).

Items are matched by type key and compared by total count, because handles
are reassigned by the game between saves and are not a stable identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from save_format import SaveInfo

from .i18n import tr


@dataclass(frozen=True)
class CompareRow:
    kind: str  # "money" | "item" | "actor"
    label: str
    before: str
    after: str


def _item_totals(info: SaveInfo) -> dict[str, tuple[int, str]]:
    totals: dict[str, tuple[int, str]] = {}
    for item in info.inventory:
        key = item.type_key or f"0x{item.handle:X}"
        count, name = totals.get(key, (0, item.display_name or key))
        totals[key] = (count + max(1, int(item.count or 1)), name)
    return totals


def compare_saves(before: SaveInfo, after: SaveInfo) -> tuple[CompareRow, ...]:
    """Differences from ``before`` to ``after``, in display order."""

    rows: list[CompareRow] = []
    if before.money != after.money:
        rows.append(CompareRow("money", tr("Деньги"), str(before.money or "—"), str(after.money or "—")))
    for field, title in (
        ("actor_health", tr("Здоровье")),
        ("actor_rank", tr("Рейтинг")),
        ("actor_reputation", tr("Репутация")),
    ):
        old, new = getattr(before, field, None), getattr(after, field, None)
        if old != new and (old is not None or new is not None):
            if field == "actor_health":
                old = None if old is None else f"{round(old * 100)}%"
                new = None if new is None else f"{round(new * 100)}%"
            rows.append(CompareRow("actor", title, str(old if old is not None else "—"), str(new if new is not None else "—")))
    first, second = _item_totals(before), _item_totals(after)
    for key in sorted(first.keys() | second.keys(), key=lambda value: (first.get(value) or second[value])[1].casefold()):
        old_count, name = first.get(key, (0, None))
        new_count, new_name = second.get(key, (0, None))
        if old_count != new_count:
            rows.append(CompareRow("item", name or new_name or key, str(old_count or "—"), str(new_count or "—")))
    return tuple(rows)


__all__ = ["CompareRow", "compare_saves"]
