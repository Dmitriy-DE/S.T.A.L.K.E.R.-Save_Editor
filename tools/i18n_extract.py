"""Collect translatable Russian source strings and check locale coverage.

    python3 tools/i18n_extract.py            # write locales/_messages.json
    python3 tools/i18n_extract.py --check    # fail on stale/missing entries

Sources: literal first arguments of ``tr()``; the three literal forms given
to ``trn()``/``count_ru()``/``plural_ru()`` (key ``one|few|many``); values of
the label tables listed in ``LABEL_TABLES``; ``t()``/``tn()`` calls of the web
client and the text nodes and titles of ``web/index.html``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "locales"
MESSAGES = LOCALES / "_messages.json"
PY_SOURCES = (
    *sorted((ROOT / "ui").glob("*.py")),
    *sorted((ROOT / "editor").glob("*.py")),
    ROOT / "web" / "web_bridge.py",
)
WEB_SOURCES = tuple(
    ROOT / "web" / name
    for name in ("app.js", "ux_copy.js", "bootstrap.js", "effects.js", "index.html")
)
# editor/s2_names.py: S2 names are composed from these translated fragments.
PAIR_TABLES = {"_MODULE_PARTS", "_UPGRADE_PARTS", "_ARMOR_EFFECTS", "_QUEST_KINDS"}
LABEL_TABLES = {
    "_EXACT",
    "_CALIBERS",
    "_ROUND_KIND",
    "_WEAPON_CLASS",
    "_ARMOR_CLASSES",
    "_FACTIONS",
    *PAIR_TABLES,
    "EQUIPMENT_CATEGORY_LABELS",
    "_SLOT_ORDER",
    "_OBSERVED_LABELS",
    "S2_REGION_NAMES",
    "_STATUS_TOOLTIPS",
    "_MONTHS_RU",
}
PLURAL_CALLS = {"trn": 1, "count_ru": 1, "plural_ru": 1}
_PLACEHOLDER = re.compile(r"\{(\d+)(?:![rsa])?(?::[^{}]*)?\}")
_CYRILLIC = re.compile("[А-Яа-яЁё]")


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def python_messages(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    singles: set[str] = set()
    plurals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "tr" and node.args:
                text = _literal(node.args[0])
                if text:
                    singles.add(text)
            elif name == "tr_in" and len(node.args) >= 2:  # tr_in(code, text)
                text = _literal(node.args[1])
                if text:
                    singles.add(text)
            elif name in PLURAL_CALLS and len(node.args) >= 4:
                forms = [_literal(arg) for arg in node.args[1:4]]
                if all(forms):
                    plurals.add("|".join(forms))  # type: ignore[arg-type]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {target.id for target in targets if isinstance(target, ast.Name)}
            if not names & LABEL_TABLES or node.value is None:
                continue
            value = node.value
            if isinstance(value, ast.Call) and value.args:  # MappingProxyType({...})
                value = value.args[0]
            if isinstance(value, ast.Dict):
                items = value.values
            elif isinstance(value, (ast.Tuple, ast.List)):
                items = value.elts
            else:
                continue
            for item in items:
                if isinstance(item, ast.Tuple):  # implicit concatenation stays one Constant
                    if names & PAIR_TABLES:
                        for element in item.elts:
                            text = _literal(element)
                            if text and _CYRILLIC.search(text):
                                singles.add(text)
                    continue
                text = _literal(item)
                if text and _CYRILLIC.search(text):
                    singles.add(text)
    return singles, plurals


_WEB_T = re.compile(r"""\bt\(\s*(["'`])((?:\\.|(?!\1).)*)\1""", re.DOTALL)
_WEB_TN = re.compile(r"""\btn\(\s*[^,]+,\s*(["'])(.*?)\1\s*,\s*(["'])(.*?)\3\s*,\s*(["'])(.*?)\5""")
_HTML_ATTRIBUTES = {"placeholder", "title", "aria-label", "alt"}


class _HtmlText(HTMLParser):
    """Text nodes and translatable attributes, as web/i18n.js translateDom sees them."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: set[str] = set()
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip += 1
        for name, value in attrs:
            if name in _HTML_ATTRIBUTES and value and value.strip():
                self.found.add(value.strip())

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.found.add(data.strip())


def web_messages(path: Path) -> tuple[set[str], set[str]]:
    if not path.is_file():
        return set(), set()
    text = path.read_text(encoding="utf-8")
    singles = {json.loads(f'"{match.group(2)}"') if match.group(1) != "`" else match.group(2)
               for match in _WEB_T.finditer(text)}
    if path.suffix == ".html":
        parser = _HtmlText()
        parser.feed(text)
        singles |= parser.found
    plurals = {f"{m.group(2)}|{m.group(4)}|{m.group(6)}" for m in _WEB_TN.finditer(text)}
    return {value for value in singles if _CYRILLIC.search(value)}, plurals


def collect() -> dict[str, list[str]]:
    singles: set[str] = set()
    plurals: set[str] = set()
    for path in PY_SOURCES:
        found, found_plurals = python_messages(path)
        singles |= found
        plurals |= found_plurals
    for path in WEB_SOURCES:
        found, found_plurals = web_messages(path)
        singles |= found
        plurals |= found_plurals
    return {"messages": sorted(singles), "plurals": sorted(plurals)}


def placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER.findall(text))


def check(catalog: dict[str, list[str]]) -> list[str]:
    problems: list[str] = []
    stored = json.loads(MESSAGES.read_text(encoding="utf-8")) if MESSAGES.is_file() else None
    if stored != catalog:
        problems.append("locales/_messages.json is stale; run python3 tools/i18n_extract.py")
    wanted = set(catalog["messages"]) | set(catalog["plurals"])
    for locale in sorted(LOCALES.glob("*.json")):
        if locale.name.startswith("_"):
            continue
        data = json.loads(locale.read_text(encoding="utf-8"))
        missing = wanted - data.keys()
        stale = data.keys() - wanted
        if missing:
            problems.append(f"{locale.name}: {len(missing)} missing, e.g. {sorted(missing)[:3]}")
        if stale:
            problems.append(f"{locale.name}: {len(stale)} stale, e.g. {sorted(stale)[:3]}")
        for key in catalog["messages"]:
            value = data.get(key)
            if isinstance(value, str) and placeholders(value) != placeholders(key):
                problems.append(f"{locale.name}: placeholder mismatch in {key!r}")
        for key in catalog["plurals"]:
            value = data.get(key)
            if value is not None and not (
                isinstance(value, list) and value and all(isinstance(item, str) for item in value)
            ):
                problems.append(f"{locale.name}: plural {key!r} must be a list of forms")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    catalog = collect()
    if args.check:
        problems = check(catalog)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    LOCALES.mkdir(exist_ok=True)
    MESSAGES.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(catalog['messages'])} messages, {len(catalog['plurals'])} plurals", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
