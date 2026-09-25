"""Interface translations keyed by the Russian source text.

Russian is the source language: ``tr("Открыть")`` returns the text unchanged
for ``ru`` and looks it up in ``locales/<code>.json`` otherwise, falling back
to the Russian text when a translation is missing.  Positional ``{0}``
placeholders are filled with :meth:`str.format` after lookup, so translators
may reorder them.

Plurals use the three Russian forms joined by ``|`` as the key; a locale maps
it to the list of forms its own CLDR rule needs (see :func:`_plural_index`).

The language is resolved once, lazily: ``STALKER_EDITOR_LANG`` → saved
preference → system locale → English.  Changing it takes effect on restart.
"""

from __future__ import annotations

import json
import locale
import os
import re
from functools import cache
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"
SOURCE_LANGUAGE = "ru"

# Languages the original trilogy or S.T.A.L.K.E.R. 2 shipped with (text or
# voice), in the order shown in settings.
LANGUAGES: dict[str, str] = {
    "ru": "Русский",
    "uk": "Українська",
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "it": "Italiano",
    "es": "Español",
    "pl": "Polski",
    "cs": "Čeština",
    "pt_BR": "Português (Brasil)",
    "tr": "Türkçe",
    "ja": "日本語",
    "ko": "한국어",
    "zh_CN": "简体中文",
    "zh_TW": "繁體中文",
}

_current: str | None = None
_PLACEHOLDER = re.compile(r"\{(\d+)(?:![rsa])?(?::[^{}]*)?\}")


def _normalise(code: str | None) -> str | None:
    if not code:
        return None
    value = code.replace("-", "_").split(".")[0].split("@")[0]
    if value in LANGUAGES:
        return value
    lowered = value.casefold()
    for known in LANGUAGES:
        if known.casefold() == lowered:
            return known
    if lowered.startswith("zh"):
        return "zh_TW" if lowered.endswith(("tw", "hk", "hant")) else "zh_CN"
    if lowered.startswith("pt"):
        return "pt_BR"
    base = lowered.split("_")[0]
    return base if base in LANGUAGES else None


def system_language() -> str:
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        found = _normalise(os.environ.get(variable, "").split(":")[0])
        if found:
            return found
    try:
        found = _normalise(locale.getlocale()[0])
    except ValueError:
        found = None
    return found or "en"


def _resolve() -> str:
    forced = _normalise(os.environ.get("STALKER_EDITOR_LANG"))
    if forced:
        return forced
    try:
        from .preferences import load_preferences

        saved = _normalise(load_preferences().language)
    except Exception:
        saved = None
    return saved or system_language()


def current_language() -> str:
    global _current
    if _current is None:
        _current = _resolve()
    return _current


def set_language(code: str | None) -> str:
    """Switch the active language (tests and first startup only)."""

    global _current
    _current = _normalise(code) or _resolve()
    return _current


@cache
def _catalog(code: str) -> dict[str, object]:
    try:
        payload = json.loads((LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _format(text: str, args: tuple[object, ...]) -> str:
    if not args:
        return text
    try:
        return text.format(*args)
    except (IndexError, KeyError, ValueError):
        return text


def tr(text: str, *args: object) -> str:
    """Translate Russian source ``text`` and fill ``{0}``-style placeholders."""

    code = current_language()
    if code != SOURCE_LANGUAGE:
        value = _catalog(code).get(text)
        if isinstance(value, str) and value:
            text = value
    return _format(text, args)


@cache
def _reverse(code: str) -> tuple[dict[str, str], tuple[tuple[re.Pattern[str], str], ...]]:
    exact: dict[str, str] = {}
    patterns: list[tuple[re.Pattern[str], str]] = []
    for source, value in _catalog(code).items():
        if not isinstance(value, str) or not value:
            continue
        if not _PLACEHOLDER.search(value):
            exact.setdefault(value, source)
            continue
        parts = _PLACEHOLDER.split(value)
        # split() yields text, index, text, index, …; rebuild as a regex.
        regex = "".join(
            re.escape(part) if position % 2 == 0 else f"(?P<p{part}_{position}>.*?)"
            for position, part in enumerate(parts)
        )
        patterns.append((re.compile(f"^{regex}$", re.DOTALL), source))
    return exact, tuple(patterns)


def source_text(text: str) -> str:
    """Map a translated message back to its Russian source for classifiers.

    Status and error messages are matched against Russian tokens in a few
    places; this keeps that logic language-independent.  Unknown text is
    returned unchanged.
    """

    code = current_language()
    if code == SOURCE_LANGUAGE or not text:
        return text
    exact, patterns = _reverse(code)
    if text in exact:
        return exact[text]
    for pattern, source in patterns:
        match = pattern.match(text)
        if match is None:
            continue
        values: dict[str, str] = {}
        for name, value in match.groupdict().items():
            values.setdefault(name[1:].split("_")[0], value)
        def fill(match: re.Match[str], found: dict[str, str] = values) -> str:
            return found.get(match.group(1), match.group(0))

        return _PLACEHOLDER.sub(fill, source)
    return text


def _plural_index(code: str, count: int) -> int:
    n = abs(int(count))
    if code in {"ru", "uk"}:
        if n % 10 == 1 and n % 100 != 11:
            return 0
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return 1
        return 2
    if code == "pl":
        if n == 1:
            return 0
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return 1
        return 2
    if code == "cs":
        return 0 if n == 1 else 1 if 2 <= n <= 4 else 2
    if code in {"ja", "ko", "zh_CN", "zh_TW", "tr"}:
        # Turkish nouns stay singular after a number.
        return 0
    if code in {"fr", "pt_BR"}:
        return 0 if n in (0, 1) else 1
    return 0 if n == 1 else 1


def trn(count: int, one: str, few: str, many: str) -> str:
    """Pick the plural form of a word for ``count`` in the active language."""

    code = current_language()
    forms: list[str] = [one, few, many]
    if code != SOURCE_LANGUAGE:
        value = _catalog(code).get(f"{one}|{few}|{many}")
        if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
            forms = value
        elif isinstance(value, str) and value:
            forms = [value]
        else:
            code = SOURCE_LANGUAGE
    index = _plural_index(code, count)
    return forms[min(index, len(forms) - 1)]


def xray_text_codes() -> tuple[tuple[str, ...], ...]:
    """Preference order of X-Ray ``text/<code>`` folders for item names."""

    code = current_language()
    by_language = {
        "ru": ("rus", "ru"),
        "uk": ("ukr", "uk", "ua"),
        "en": ("eng", "en"),
        "de": ("ger", "de", "deu"),
        "fr": ("fra", "fr", "fre"),
        "it": ("ita", "it"),
        "es": ("spa", "es", "esp"),
        "pl": ("pol", "pl"),
        "cs": ("cze", "cs", "ces"),
    }
    order = [by_language.get(code, ())]
    if code == "uk":
        order += [by_language["en"], by_language["ru"]]
    elif code == "ru":
        order += [by_language["en"]]
    else:
        order += [by_language["en"], by_language["ru"]]
    return tuple(codes for codes in order if codes)


__all__ = [
    "LANGUAGES",
    "LOCALES_DIR",
    "current_language",
    "set_language",
    "source_text",
    "system_language",
    "tr",
    "trn",
    "xray_text_codes",
]
