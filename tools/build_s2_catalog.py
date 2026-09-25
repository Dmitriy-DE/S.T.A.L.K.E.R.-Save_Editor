#!/usr/bin/env python3
"""Build S.T.A.L.K.E.R. 2 item names and icons (``web/s2_items.json``).

The editor reads no S.T.A.L.K.E.R. 2 install, so the names players know come
from published sources, in this order of trust:

1. the game's own Russian string table, which the Russian S.T.A.L.K.E.R.
   Wiki publishes verbatim as ``Module:S2Localization`` (``sid_items_<SID>_name``,
   ``sid_questItemprototypes_<SID>_name``, ``sid_upgrades_<SID>_name``);
2. the English wiki's item infoboxes, which record the SID (``code`` /
   ``hoc_code``), the English name, the icon and — for unique weapons — the
   base weapon ("a unique AR416");
3. ``data/s2_sources.json``: hand-matched fextralife names and pictures and a
   SID → English list cross-checked against (1);
4. interlanguage links for the other wiki languages.

Each icon is downloaded once, converted to PNG no larger than 160×120 and
stored as ``assets/icons/s2/<SID>.png`` (mirrored to ``web/icons/s2``).
Presentation only: nothing here reaches a save writer.

Usage:
    python tools/build_s2_catalog.py [--no-icons]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "web" / "s2_items.json"
ICON_DIR = ROOT / "assets" / "icons" / "s2"
WEB_ICON_DIR = ROOT / "web" / "icons" / "s2"
SOURCES = ROOT / "data" / "s2_sources.json"
API = "https://stalker.fandom.com{prefix}/api.php"
USER_AGENT = "S.T.A.L.K.E.R.-Save_Editor catalog builder (github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor)"
# Wiki language prefix → interface language.
LANGUAGES = {"ru": "ru", "uk": "uk", "de": "de", "fr": "fr", "it": "it", "es": "es", "pl": "pl", "cs": "cs", "pt-br": "pt_BR", "tr": "tr", "ja": "ja", "ko": "ko", "zh": "zh_CN"}
_LOCALIZATION_PARTS = 5
_STRING = re.compile(r'^\s*(?:\["([^"]+)"\]|([A-Za-z0-9_]+))\s*=\s*"((?:[^"\\]|\\.)*)"', re.MULTILINE)
_NAME_KEY = re.compile(r"^sid_(?:items|questItemprototypes|upgrades)_(.+)_name$")
_FIELD = r"^\s*\|\s*(?:{name})\s*=\s*(.*?)\s*$"
_FILE = re.compile(r"(?:File|Файл|Image|Изображение):\s*([^|\]]+)", re.IGNORECASE)
_S2 = re.compile(r"\{\{\s*GameIcon\s*\|\s*s2\b|\{\{\s*HoC\b|Heart of Chornobyl|hoc_code", re.IGNORECASE)
_UNIQUE = re.compile(r"is a unique \[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_MAX_ICON = (160, 120)


def _get(prefix: str, **params: str) -> dict:
    params.setdefault("format", "json")
    params.setdefault("action", "query")
    url = API.format(prefix=prefix) + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except OSError:
            time.sleep(1 + attempt * 2)
    raise SystemExit(f"wiki request failed: {url}")


def _paged(prefix: str, key: str, **params: str):
    cont: dict[str, str] = {}
    while True:
        data = _get(prefix, **params, **cont)
        yield from data.get("query", {}).get(key, [])
        if "continue" not in data:
            return
        cont = {k: str(v) for k, v in data["continue"].items()}


def _wikitext(page: dict) -> str:
    return (page.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")


def _field(text: str, *names: str) -> str | None:
    match = re.search(_FIELD.format(name="|".join(names)), text, re.MULTILINE)
    return match.group(1) if match and match.group(1).strip() else None


def _plain(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"<!--.*?-->|\[\[(?:[^|\]]*\|)?([^\]]*)\]\]|'''?|\{\{[^}]*\}\}", r"\1", value)
    value = value.strip().strip('"').strip()
    return value or None


def _file(value: str | None) -> str | None:
    """``[[Файл:Icon HoC item Battery.png|100px]]`` or a bare name → file name."""

    if not value:
        return None
    match = _FILE.search(value)
    name = (match.group(1) if match else value).strip()
    return name if re.search(r"\.(?:png|jpe?g|webp|gif)$", name, re.IGNORECASE) else None


def _sid(value: str | None) -> str | None:
    value = re.sub(r"^sid_(?:items|questItemprototypes)_", "", str(value or "").strip())
    # The wiki keeps the player's copy of a unique weapon (``_Player``).
    value = re.sub(r"_Player$", "", value)
    # S2 SIDs are CamelCase; lowercase ids are trilogy sections (wpn_ak74).
    return value if re.fullmatch(r"[A-Z][A-Za-z0-9_]*", value or "") else None


def _batches(prefix: str, titles: list[str], **params: str):
    for start in range(0, len(titles), 50):
        data = _get(prefix, titles="|".join(titles[start : start + 50]), **params)
        yield from data.get("query", {}).get("pages", {}).values()


def _template_pages(prefix: str, template_prefix: str, pattern: str) -> list[str]:
    templates = [
        page["title"]
        for page in _paged(prefix, "allpages", list="allpages", apnamespace="10", apprefix=template_prefix, aplimit="500")
        if re.search(pattern, page["title"])
    ]
    titles: set[str] = set()
    for template in templates:
        for page in _paged(prefix, "embeddedin", list="embeddedin", eititle=template, eilimit="500", einamespace="0"):
            titles.add(page["title"])
    return sorted(titles)


def _plain_title(title: str) -> str:
    # "Батарейка/«Сердце Чернобыля»" and "Вихрь (артефакт)" → the item name.
    return re.sub(r"\s*\([^)]*\)$", "", title.split("/", 1)[0]).strip()


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _unescape(value: str) -> str:
    escapes = {"n": "\n", "r": "\r", "t": "\t"}
    return re.sub(r"\\(.)", lambda m: escapes.get(m.group(1), m.group(1)), value)


def official_russian() -> dict[str, str]:
    """SID → the game's own Russian name (items, quest items, upgrades)."""

    names: dict[str, str] = {}
    for part in range(1, _LOCALIZATION_PARTS + 1):
        title = f"Module:S2Localization/data/ru/part{part}"
        for page in _batches("/ru", [title], prop="revisions", rvprop="content", rvslots="main"):
            for match in _STRING.finditer(_wikitext(page)):
                key = match.group(1) or match.group(2)
                sid = _NAME_KEY.match(key)
                value = _unescape(match.group(3)).strip()
                if sid and value and value.casefold() != "test":
                    names.setdefault(sid.group(1), value)
    return names


def collect() -> dict[str, dict]:
    items: dict[str, dict] = {}
    translations: dict[str, dict[str, str]] = {}

    def entry(code: str) -> dict:
        return items.setdefault(code, {"names": {}})

    for code, name in official_russian().items():
        entry(code)["names"]["ru"] = name
    print(f"{len(items)} official Russian names", file=sys.stderr)

    # Russian wiki: ``techname`` holds the SID, ``icon`` the inventory icon.
    ru_titles = _template_pages("/ru", "Card_", r"Ammo|Armor|Artefact|Detector|Drug|Grenade|Item|Weapon")
    for page in _batches("/ru", ru_titles, prop="revisions|langlinks", rvprop="content", rvslots="main", lllimit="500"):
        text = _wikitext(page)
        english = next((_plain_title(link["*"]) for link in page.get("langlinks", []) if link.get("lang") == "en"), None)
        if english:
            translations.setdefault(english, {}).setdefault("ru", _plain_title(page["title"]))
        techname = _sid(_field(text, "techname"))
        if not techname:
            continue
        item = entry(techname)
        item["names"].setdefault("ru", _plain_title(page["title"]))
        icon = _file(_field(text, "icon")) or _file(_field(text, "image"))
        if icon:
            item.setdefault("ru_icon", icon)
        if english:
            item["names"].setdefault("en", english)
    # English wiki: infoboxes of S.T.A.L.K.E.R. 2 pages carry the SID.
    en_titles = _template_pages("", "Infobox", r".")
    for page in _batches("", en_titles, prop="revisions|langlinks", rvprop="content", rvslots="main", lllimit="500"):
        text = _wikitext(page)
        links = {
            LANGUAGES[link["lang"]]: _plain_title(link["*"])
            for link in page.get("langlinks", [])
            if link.get("lang") in LANGUAGES and link.get("*")
        }
        for language, name in links.items():
            translations.setdefault(_plain_title(page["title"]), {}).setdefault(language, name)
        if not _S2.search(text):
            continue
        for raw in re.findall(r"^\s*\|\s*(?:hoc_)?code\s*=\s*(\S+)\s*$", text, re.MULTILINE):
            sid = _sid(raw)
            if not sid:
                continue
            item = entry(sid)
            english = _plain(_field(text, "hoc_name", "name")) or _plain_title(page["title"])
            item["names"]["en"] = english
            icon = _file(_field(text, "hoc_icon", "icon")) or _file(_field(text, "hoc_image", "image"))
            if icon:
                item.setdefault("en_icon", icon)
            unique = _UNIQUE.search(text)
            if unique:
                item["variant_of"] = _plain_title(unique.group(1))
            for language, name in links.items():
                item["names"].setdefault(language, name)
    print(f"{len(ru_titles)} ru pages, {len(en_titles)} en pages", file=sys.stderr)

    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    # Hand-matched fextralife names and pictures, then the SID list.
    for code, (english, image) in {**sources["weapons"], **sources["consumables"]}.items():
        item = entry(code)
        # Hand-checked against the official Russian name: wins over the wiki.
        item["names"]["en"] = english
        if image:
            item.setdefault("image_url", image)
    for code, english in sources["english_names"].items():
        entry(code)["names"].setdefault("en", english)
    # Researched gap fills: only where nothing better is known.
    for code, (english, image) in sources.get("gap_fills", {}).items():
        item = entry(code)
        item["names"].setdefault("en", english)
        if image:
            item.setdefault("image_url", image)
    by_name = {_norm(name): url for name, url in sources["images_by_name"].items()}
    for item in items.values():
        english = item["names"].get("en")
        if not english:
            continue
        for language, name in translations.get(english, {}).items():
            item["names"].setdefault(language, name)
        if "image_url" not in item and _norm(english) in by_name:
            item["image_url"] = by_name[_norm(english)]
    return items


def _icon_urls(prefix: str, files: list[str]) -> dict[str, str]:
    urls: dict[str, str] = {}
    for start in range(0, len(files), 50):
        data = _get(
            prefix,
            prop="imageinfo",
            iiprop="url",
            titles="|".join(f"File:{name}" for name in files[start : start + 50]),
        )
        query = data.get("query", {})
        back = {n["to"]: n["from"] for n in query.get("normalized", [])}
        for page in query.get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("url"):
                title = back.get(page["title"], page["title"])
                urls[title.split(":", 1)[-1]] = info["url"]
    return urls


def _store_icon(raw: bytes, target: Path) -> bool:
    """Save any image the sources serve (PNG/WebP/JPEG) as a small PNG."""

    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QImage

    image = QImage.fromData(QByteArray(raw))
    if image.isNull():
        return False
    width, height = _MAX_ICON
    if image.width() > width or image.height() > height:
        image = image.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return image.save(str(target), "PNG")  # type: ignore[call-overload]  # PySide6 stub wants bytes, runtime wants str


def download_icons(items: dict[str, dict]) -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    en_urls = _icon_urls("", sorted({i["en_icon"] for i in items.values() if i.get("en_icon")}))
    ru_urls = _icon_urls("/ru", sorted({i["ru_icon"] for i in items.values() if i.get("ru_icon")}))
    for code, entry in sorted(items.items()):
        target = ICON_DIR / f"{code}.png"
        if not target.is_file():
            urls = [
                url
                for url in (en_urls.get(entry.get("en_icon", "")), ru_urls.get(entry.get("ru_icon", "")), entry.get("image_url"))
                if url
            ]
            for url in urls:
                # The fextralife image CDN rejects non-browser user agents.
                agent = "Mozilla/5.0" if "fextralife" in url else USER_AGENT
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": agent})
                    with urllib.request.urlopen(request, timeout=30) as response:
                        if _store_icon(response.read(), target):
                            break
                except OSError:
                    continue
        if target.is_file():
            entry["icon"] = f"s2/{code}.png"
    if WEB_ICON_DIR.exists():
        shutil.rmtree(WEB_ICON_DIR)
    shutil.copytree(ICON_DIR, WEB_ICON_DIR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-icons", action="store_true")
    args = parser.parse_args(argv)
    from PySide6.QtGui import QGuiApplication

    _app = QGuiApplication.instance() or QGuiApplication(["build_s2_catalog"])
    items = collect()
    if not args.no_icons:
        download_icons(items)
    for entry in items.values():
        for key in ("en_icon", "ru_icon", "image_url"):
            entry.pop(key, None)
    payload = {
        "schema_version": 2,
        "source": (
            "Russian names: the game's string table as published by the Russian S.T.A.L.K.E.R. Wiki; "
            "English names, icons and variants: S.T.A.L.K.E.R. Wiki (stalker.fandom.com, CC BY-SA 3.0), "
            "stalker2.wiki.fextralife.com and data/s2_sources.json. Names and icons only."
        ),
        "items": dict(sorted(items.items())),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with_icons = sum(1 for entry in items.values() if entry.get("icon"))
    with_english = sum(1 for entry in items.values() if entry["names"].get("en"))
    print(f"{len(items)} S2 items ({with_english} with English names), {with_icons} icons -> {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
