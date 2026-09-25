"""Safe presentation labels for S.T.A.L.K.E.R. 2 save-local item names.

These labels are deliberately a tiny presentation layer for names that were
observed in the supplied save corpus. They do not turn a save-local name into
a Zone Kit SID, a catalog constructor, or a writer capability. An unknown
name is returned unchanged so diagnostics never lose the serialized
identifier.
"""

from __future__ import annotations

from types import MappingProxyType

from .i18n import tr

_OBSERVED_LABELS = MappingProxyType(
    {
        "gunkharod_st": "Kharod",
        "guardgunlavina_st": "СА «Лавина»",
        "gunlavina_st": "СА «Лавина»",
        "gun_d12": "Сайга Д-12",
        "gund12_st": "Сайга Д-12",
        "gund12_sg": "Сайга Д-12",
        "gun_skifgun_hg": "Пистолет Скифа",
        "gunpm_hg": "ПМ",
        "nvg_gen2": "ПНВ (2-е поколение)",
        "nvg_gen3": "ПНВ (3-е поколение)",
        "nvg_npc_gen2": "ПНВ (2-е поколение)",
        "nvg_npc_gen3": "ПНВ (3-е поколение)",
        "binoculars_02": "Бинокль",
        "binoculars_03": "Бинокль",
        "binoculars_npc": "Бинокль",
    }
)


def s2_presentation_name(value: str | None) -> str | None:
    """Return a corpus-backed human label without changing the raw key."""

    normalized = str(value or "").strip()
    if not normalized:
        return None
    label = _OBSERVED_LABELS.get(normalized.casefold())
    return tr(label) if label is not None else normalized


__all__ = ["s2_presentation_name"]
