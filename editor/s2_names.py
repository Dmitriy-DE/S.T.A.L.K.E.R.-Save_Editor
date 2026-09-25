"""Readable names for S.T.A.L.K.E.R. 2 save-local SIDs.

The game's own localisation lives in encrypted-free but IoStore-packed
``.locres`` files the editor does not read.  Instead, well-known SIDs get an
explicit name and structured SIDs (rounds, weapons, modules, upgrades, quest
items) are composed from translated fragments.  Anything unknown falls back
to a tidied version of the SID, never to an empty label.
"""

from __future__ import annotations

import re

from .i18n import tr
from .official_names import official_name
from .s2_items import s2_official_name

# Consumables, grenades and a few unique weapons whose names are certain.
_EXACT: dict[str, str] = {
    "bandage": "Бинт",
    "medkit": "Аптечка",
    "armymedkit": "Армейская аптечка",
    "ecomedkit": "Научная аптечка",
    "antirad": "Антирад",
    "energetic": "Энергетик",
    "hercules": "Геркулес",
    "beer": "Пиво",
    "vodka": "Водка",
    "water": "Вода",
    "sausage": "Колбаса",
    "cannedfood": "Консервы",
    "bread": "Хлеб",
    "psyblockade": "Пси-блокада",
    "grenadergd5": "Граната РГД-5",
    "grenadef1": "Граната Ф-1",
    "electrocollar": "Электроошейник",
    "vartadogtag": "Жетон «Варты»",
    "gunkharod_st": "Kharod",
    "guardgunlavina_st": "СА «Лавина»",
    "gunlavina_st": "СА «Лавина»",
    "gund12_sg": "Сайга Д-12",
    "gund12_st": "Сайга Д-12",
    "gun_skifgun_hg": "Пистолет Скифа",
    "gunpm_hg": "ПМ",
    "nvg_gen1": "ПНВ (1-е поколение)",
    "nvg_gen2": "ПНВ (2-е поколение)",
    "nvg_gen3": "ПНВ (3-е поколение)",
    "nvg_npc_gen1": "ПНВ (1-е поколение)",
    "nvg_npc_gen2": "ПНВ (2-е поколение)",
    "nvg_npc_gen3": "ПНВ (3-е поколение)",
    "binoculars_npc": "Бинокль",
    "binoculars_02": "Бинокль",
    "binoculars_03": "Бинокль",
}

_CALIBERS = {
    "012": "12 калибр",
    "045": ".45 ACP",
    "545": "5,45×39 мм",
    "556": "5,56×45 мм",
    "762nato": "7,62×51 мм",
    "762sniper": "7,62×54 мм",
    "762": "7,62×39 мм",
    "919": "9×19 мм",
    "939": "9×39 мм",
    "918": "9×18 мм",
    "338": ".338",
}
_ROUND_KIND = {"d": "", "a": "бронебойные", "s": "экспансивные"}

_WEAPON_CLASS = {
    "st": "автомат",
    "sg": "дробовик",
    "sp": "снайперская винтовка",
    "hg": "пистолет",
    "pp": "пистолет-пулемёт",
    "mg": "пулемёт",
    "gl": "гранатомёт",
}

_MODULE_PARTS = (
    ("magincreased", "Увеличенный магазин"),
    ("maglarge", "Большой магазин"),
    ("magpaired", "Спаренный магазин"),
    ("magdefault", "Стандартный магазин"),
    ("goloscope", "Голографический прицел"),
    ("x2scope", "Прицел 2×"),
    ("x4scope", "Прицел 4×"),
    ("x6scope", "Прицел 6×"),
    ("scope", "Прицел"),
    ("silen", "Глушитель"),
    ("laser", "Лазерный целеуказатель"),
    ("grip", "Рукоять"),
    ("toprail", "Верхняя планка"),
    ("screw", "Резьбовой адаптер"),
)

_UPGRADE_PARTS = (
    ("offset_stock", "Смещённый приклад"),
    ("handguard", "Цевьё"),
    ("barrel", "Ствол"),
    ("body", "Корпус"),
    ("stock", "Приклад"),
    ("grip", "Рукоять"),
    ("rail", "Планка"),
    ("laser", "Лазерный целеуказатель"),
    ("magazine", "Магазин"),
    ("scope", "Прицел"),
)

_ARMOR_EFFECTS = (
    ("protectionthermal_protectionchemica", "Термо- и химзащита"),
    ("exoprotectionphysical", "Защита от пуль"),
    ("protectionphysical", "Защита от пуль"),
    ("exomaxdurability", "Прочность"),
    ("maxdurability", "Прочность"),
    ("protectionradiation", "Защита от радиации"),
    ("protectionchemical", "Химзащита"),
    ("protectionthermal", "Термозащита"),
    ("protectionelectrical", "Электрозащита"),
    ("carryingcapacity", "Переносимый вес"),
    ("reductionweight", "Снижение веса"),
    ("addruneffect", "Выносливость при беге"),
    ("rad_container", "Контейнер для артефакта"),
    ("psy", "Пси-защита"),
    ("bleeding", "Защита от кровотечения"),
    ("stamina", "Выносливость"),
)

_QUEST_KINDS = (
    ("Key[Cc]ard", "Ключ-карта"),
    ("PDA", "КПК"),
    ("Keys", "Ключи"),
    ("Key", "Ключ"),
    ("Chevron", "Шеврон"),
    ("Doc", "Документ"),
    ("Journal", "Журнал"),
    ("Map", "Карта"),
    ("Loot", "Трофей"),
    ("Dog[Tt]ag", "Жетон"),
)
_QUEST_PREFIX = re.compile(r"^(?:dlc\d+_)?(?:[a-z]\d+_)?(?:(?:mq|sq|eq)\d+_)*", re.IGNORECASE)


def _words(value: str) -> str:
    """``WeirdBall`` → ``Weird Ball``; ``rad_container`` → ``rad container``."""

    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", value)
    return re.sub(r"[_\s]+", " ", spaced).strip()


def _round(sid: str) -> str | None:
    match = re.fullmatch(r"a(\d{3})(nato|sniper)?([das])", sid.casefold())
    if match is None:
        return None
    caliber = _CALIBERS.get(match.group(1) + (match.group(2) or "")) or _CALIBERS.get(match.group(1))
    if caliber is None:
        return None
    kind = _ROUND_KIND[match.group(3)]
    return tr(caliber) + (f" · {tr(kind)}" if kind else "")


def _tier(rest: str) -> str:
    numbers = re.findall(r"\d+", rest)
    return tr(" · ур. {0}", numbers[0]) if numbers else ""


def _weapon(sid: str) -> str | None:
    parts = re.sub(r"^(?:Guard)?Gun_?", "", sid, flags=re.IGNORECASE).split("_")
    if len(parts) < 2 or parts[-1].casefold() not in _WEAPON_CLASS:
        return None
    model = re.sub(r"Gun$", "", "_".join(parts[:-1]))
    if not model:
        return None
    return f"{_words(model)} ({tr(_WEAPON_CLASS[parts[-1].casefold()])})"


def _module(sid: str) -> str | None:
    lowered = sid.casefold()
    for token, label in _MODULE_PARTS:
        if token in lowered:
            return tr(label) + _tier(lowered.split(token, 1)[1])
    return None


def _weapon_upgrade(sid: str) -> str | None:
    match = re.search(r"_upgrade_(?:attachment_)?(.+)$", sid, re.IGNORECASE)
    if match is None:
        return None
    rest = match.group(1).casefold()
    for token, label in _UPGRADE_PARTS:
        if rest.startswith(token):
            return tr(label) + _tier(rest[len(token) :])
    return None


def _armor_upgrade(sid: str) -> str | None:
    match = re.search(r"_(?:armor|helmet)_(.+?)_(?:left|right|center)_(\d+)", sid, re.IGNORECASE)
    if match is None:
        return None
    effect = match.group(1).casefold()
    for token, label in _ARMOR_EFFECTS:
        if effect.startswith(token):
            return tr(label) + tr(" · ур. {0}", match.group(2))
    return _words(match.group(1)) + tr(" · ур. {0}", match.group(2))


def _artifact(sid: str) -> str | None:
    match = re.fullmatch(r"[A-Z]Artifact([A-Za-z0-9]+)", sid)
    return _words(match.group(1)).replace("Rubiks", "Rubik's") if match else None


def _quest(sid: str) -> str | None:
    for token, label in _QUEST_KINDS:
        # CamelCase/underscore boundaries only: "unmapped" is not a map.
        pattern = rf"(?:^|_|(?<=[a-z0-9])){token}(?=$|_|\d|[A-Z])"
        if re.search(pattern, sid):
            core = re.sub(pattern, " ", _QUEST_PREFIX.sub("", sid))
            detail = _words(core).strip(" _-")
            return f"{tr(label)}: {detail}" if detail else tr(label)
    return None


_ARMOR_CLASSES = {
    "exoskeleton": "Экзоскелет",
    "heavy": "Тяжёлая броня",
    "battle": "Боевая броня",
    "middle": "Средняя броня",
    "light": "Лёгкая броня",
    "jacket": "Куртка",
    "rook": "Броня «Грач»",
    "anomaly": "Аномальный комбинезон",
    "seva": "Комбинезон «СЕВА»",
    "sevav": "Комбинезон «СЕВА-В»",
    "sevad": "Комбинезон «СЕВА-Д»",
    "sevai": "Комбинезон «СЕВА-И»",
}
_FACTIONS = {
    "monolith": "Монолит",
    "svoboda": "Свобода",
    "dolg": "Долг",
    "bandit": "Бандиты",
    "neutral": "Одиночки",
    "scientific": "Учёные",
    "varta": "Варта",
    "military": "Военные",
    "mercenaries": "Наёмники",
    "mercenary": "Наёмники",
    "spark": "Искра",
    "corps": "Корпус",
    "noon": "Полдень",
    "ward": "Варта",
}


def _armor(sid: str) -> str | None:
    match = re.fullmatch(r"([A-Za-z]+)_([A-Za-z]+)_(Armor|Helmet)", sid)
    if match is None:
        return None
    base = _ARMOR_CLASSES.get(match.group(1).casefold())
    label = tr(base) if base else _words(match.group(1))
    if match.group(3) == "Helmet":
        label = tr("Шлем")
    faction = _FACTIONS.get(match.group(2).casefold())
    return f"{label} · {tr(faction) if faction else _words(match.group(2))}"


# S2 devices that share their official name with the trilogy: the
# Enhanced Edition snapshot has those names in 13 languages.
_TRILOGY_TWINS = {
    "echo": "detector_simple",
    "bear": "detector_advanced",
    "veles": "detector_elite",
    "binoculars_01": "wpn_binoc",
    "binoculars_02": "wpn_binoc",
    "binoculars_03": "wpn_binoc",
    "binoculars_npc": "wpn_binoc",
}


def _blueprint(sid: str) -> str | None:
    match = re.fullmatch(r"Blueprint_(.+?)(?:_Upgrade)?_(\d+)", sid, re.IGNORECASE)
    if match is None:
        return None
    weapon = next(
        (name for name in (s2_official_name(f"Gun{match.group(1)}_{suffix}") for suffix in ("ST", "HG", "PP", "SG", "SP", "MG", "AR")) if name),
        None,
    )
    return f"{tr('Чертёж')}: {weapon or _words(match.group(1))}" + tr(" · ур. {0}", match.group(2))


def s2_readable_name(sid: str | None, *, kind_code: int | None = None) -> str | None:
    """Return a readable label for an S2 SID, or ``None`` for an empty SID."""

    value = str(sid or "").strip()
    if not value:
        return None
    official = s2_official_name(value)
    if official:
        return official
    twin = _TRILOGY_TWINS.get(value.casefold())
    if twin is not None:
        official = official_name("stalker-cop", "items", twin)
        if official:
            return official
    exact = _EXACT.get(value.casefold())
    if exact is not None:
        return tr(exact)
    blueprint = _blueprint(value)
    if blueprint is not None:
        return blueprint
    for resolver in (_armor_upgrade, _weapon_upgrade, _round, _artifact, _armor):
        label = resolver(value)
        if label:
            return label
    if kind_code == 0 or re.match(r"^(?:guard)?gun", value, re.IGNORECASE):
        if re.search(r"_(?:mag|screw)|silen|scope|laser|grip|toprail", value, re.IGNORECASE):
            label = _module(value)
            if label:
                return label
        label = _weapon(value)
        if label:
            return label
    label = _module(value) if re.match(r"^(?:en|ru|hp)_|toprail", value, re.IGNORECASE) else None
    if label:
        return label
    if kind_code == 8 or kind_code is None:
        label = _quest(value)
        if label:
            return label
    return _words(value)


__all__ = ["s2_readable_name"]
