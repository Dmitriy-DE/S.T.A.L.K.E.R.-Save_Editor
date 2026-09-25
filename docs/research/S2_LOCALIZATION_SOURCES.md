> Черновик Gemini (2026-09-26), Claude не перепроверял. Утверждения без доказательства на реальных сейвах — гипотезы. Лицензии внешних дампов (например, `Trasiankus/stalker2-bel`) до использования в сборке проверить отдельно.

# Публичные источники официальных названий предметов S.T.A.L.K.E.R. 2 на других языках

Ресерч выполнен в рамках задачи **KB-6** (2026-09-25) для поддержки многоязычного каталога предметов S.T.A.L.K.E.R. 2: Heart of Chornobyl в редакторе сохранений.

Целевые языки игры: **uk, de, fr, pl, es, it, cs, ja, ko, zh (zh_CN, zh_TW), tr, pt-BR** (+ уже интегрированные **ru** и **en**).

---

## 1. Текущее состояние в проекте

На данный момент в [web/s2_items.json](file:///home/dmytro/Projects/save-editor/web/s2_items.json) покрытие именами по языкам распределено неравномерно:
- **ru:** 1375 предметов (100% из русской таблицы локализации `Module:S2Localization` на Fandom);
- **en:** 349 предметов (ручная выверка + карточки инфобоксов en-вики);
- **uk:** 141 предмет (только интервики-ссылки `langlinks` со страниц en-вики);
- **pl:** 67 предметов (интервики-ссылки);
- **fr:** 25 предметов (интервики-ссылки);
- **de, es, it, cs, ja, ko, zh_CN, tr, pt_BR:** 0 предметов (на соответствующих языковых поддоменах Fandom отдельные статьи по большинству предметов S2 отсутствуют).

Интервики-ссылки MediaWiki не способны обеспечить полное покрытие для новых игр, так как фанатские сообщества на не-английских языках создают статьи медленно и фрагментарно. Необходимы прямые дампы оригинальных языковых таблиц игры.

---

## 2. Анализ источников

### Источник A: GSC Zone Kit — `TextDatabase.json` (Эталонный официальный источник)

- **Ссылка / Путь:** `Stalker2/Content/TextToolBackup/TextDatabase.json` внутри официального дистрибутива Zone Kit.
- **Документация GSC:** [Mod TextTool Guide (PDF)](https://cdn.stalker2.com/guides/Mod_TextTool.pdf), стр. 1:
  > *«The Stalker2\\Content\\TextToolBackup\\TextDatabase.json file contains all of the vanilla localized texts and is read by Zone Kit at startup.»*
- **Поддерживаемые языки:** Все 15 официальных языков игры:
  - `en` (English)
  - `uk` (Ukrainian)
  - `ru` (Russian)
  - `de` (German)
  - `fr` (French)
  - `pl` (Polish)
  - `es` (Spanish - Spain)
  - `it` (Italian)
  - `cs` (Czech)
  - `ja` (Japanese)
  - `ko` (Korean)
  - `zh_CN` (Chinese Simplified)
  - `zh_TW` (Chinese Traditional)
  - `tr` (Turkish)
  - `pt_BR` (Portuguese - Brazil)
- **Покрытие:** 100% всех строк игры (включая оружие, броню, патроны, квестовые предметы, заметки, модификации).
- **Формат:** Чистый валидный UTF-8 JSON со структурой SID → язык → текст.
- **Лицензия и условия:** Zone Kit распространяется бесплатно разработчиками (GSC Game World) через Epic Games Store и Steam для моддинга S.T.A.L.K.E.R. 2. Использование названий предметов подпадает под добросовестное использование (presentation / catalog purposes) без нарушения проприетарного кода.
- **Как получить машинно:** Прямое чтение файла:
  ```python
  import json
  with open("TextDatabase.json", encoding="utf-8") as f:
      db = json.load(f)
  ```
- **Оценка:** Наилучший первоисточник для долгосрочной полной локализации.

---

### Источник B: GitHub-репозиторий `Trasiankus/stalker2-bel` (`localization.json`)

- **Ссылка:** https://github.com/Trasiankus/stalker2-bel
- **Прямой URL данных:** https://raw.githubusercontent.com/Trasiankus/stalker2-bel/main/localization.json
- **Размер файла:** ~16.9 МБ.
- **Поддерживаемые языки:**
  - `ua` (`uk`) — 100% официальный украинский текст из ванильной игры;
  - `ru` — 100% официальный русский текст из ванильной игры;
  - `bel` — фанатский белорусский перевод.
- **Покрытие для украинского языка:** 100% (все ключи `sid_items_*_name`, `sid_questItemprototypes_*_name`, `sid_upgrades_*_name`, `sid_character_*`).
- **Формат:** JSON:
  ```json
  {
    "sid_items_GunTOZ_SG_name": {
      "ua": "ТОЗ-34",
      "ru": "ТОЗ-34",
      "bel": "ТОЗ-34"
    },
    "sid_items_Bread_name": {
      "ua": "Хліб",
      "ru": "Хлеб",
      "bel": "Хлеб"
    }
  }
  ```
- **Лицензия и условия:** Публичный открытый репозиторий на GitHub. Исходные тексты `ua` и `ru` взяты напрямую из игры и обновляются скриптом `make_mod.py`.
- **Как получить машинно:**
  ```python
  import urllib.request, json

  URL = "https://raw.githubusercontent.com/Trasiankus/stalker2-bel/main/localization.json"
  req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=30) as resp:
      data = json.loads(resp.read().decode("utf-8"))
  # Ключи предметов: sid_items_<SID>_name -> data[key]["ua"]
  ```
- **Оценка:** Готовое немедленное решение для закрытия 100% украинской локализации (`uk`) без необходимости иметь установленный Zone Kit на машине сборки.

---

### Источник C: Распаковка ванильного архива `LocalizationDB.ubulk` через FModel / S2HOC_LocEditor

- **Инструменты:**
  - **FModel:** https://github.com/4sval/FModel (просмотр и распаковка UE5-паков `.utoc`/`.ucas`);
  - **S2HOC Localization Editor:** доступен на AP-PRO и Nexus Mods;
  - **UnrealReZen:** https://github.com/rm-NoobInCoding/UnrealReZen.
- **Путь в архивах игры:** `Stalker2/Content/Localization/Game/LocalizationDB.ubulk` и `.uasset`.
- **Поддерживаемые языки:** Все 15 официальных языков игры.
- **Покрытие:** 100% ванильного текста текущей установленной версии игры.
- **Формат:** Конвертируется утилитой `S2HOC_LocEditor` в единый `LocalizationDB.json`.
- **Лицензия и условия:** Требуется наличие купленной установленной игры у разработчика для однократного экспорта.
- **Как получить машинно:** Экспорт через консольный вызов утилит распаковщика или использование готового сконвертированного JSON.
- **Оценка:** Полный аналог источника A, если Zone Kit не установлен, но установлена сама игра.

---

### Источник D: MediaWiki API (Fandom S.T.A.L.K.E.R. Wikis)

- **Ссылки:**
  - Русская вики: `https://stalker.fandom.com/ru/api.php` (страницы `Module:S2Localization/data/ru/part1` .. `part5`);
  - Английская вики: `https://stalker.fandom.com/api.php` (`Infobox Item` с параметрами `hoc_code`, `code`);
  - Языковые поддомены: `/uk/`, `/pl/`, `/de/`, `/fr/`, `/es/`, `/cs/`, `/it/`.
- **Поддерживаемые языки:**
  - `ru`: 100% (уже интегрировано через парсинг модуля Lua);
  - `en`: ~25% через инфобоксы, остальное — дополняется ручной таблицей;
  - `uk`, `pl`, `fr`, `de`, `es`: крайне низкое (<5–10% предметов).
- **Лицензия:** Creative Commons Attribution-ShareAlike 3.0 (CC BY-SA 3.0).
- **Как получить машинно:** Запросы к MediaWiki API (`tools/build_s2_catalog.py`).
- **Оценка:** Для русского языка модуль Fandom идеален. Для остальных 13 языков этот источник не подходит из-за отсутствия статей по большинству предметов в региональных вики.

---

### Источник E: Фанатские платформы моддинга (Nexus Mods / AP-PRO)

- **Проекты:**
  - *Merged Localization for S.T.A.L.K.E.R. 2* (Nexus Mods);
  - *S.T.A.L.K.E.R. 2 Pak Cfg Merge Tool* (GitHub / Nexus).
- **Специфика:** Моды локализации на Nexus в основном решают проблему конфликта модов (движок S2 читает только один активный файл локализации). Большинство модов представляют собой модифицированные дампы `LocalizationDB.json`.
- **Оценка:** Для редактора сохранений использовать фанатские модпаки не рекомендуется, так как они могут содержать изменённые или нестандартные названия. Нужны только чистые ванильные строки.

---

## 3. Сводная таблица источников

| Источник | Языки | Покрытие S2 | Формат | Машинный доступ | Лицензионная чистота |
|---|---|---|---|---|---|
| **Zone Kit (`TextDatabase.json`)** | Все 15 языков (uk, de, fr, pl, es, it, cs, ja, ko, zh_CN, zh_TW, tr, pt_BR) | **100%** | JSON | Прямой локальный `json.load()` | Официальный бесплатный SDK GSC |
| **`Trasiankus/stalker2-bel`** | `uk`, `ru` | **100%** | JSON | `curl` с GitHub без авторизации | Открытый репозиторий GitHub (дамп ваниллы) |
| **`LocalizationDB.ubulk` (FModel / LocEditor)** | Все 15 языков | **100%** | Двоичный `.ubulk` → JSON | Локальный скрипт распаковки | Ресурсы купленной игры |
| **Fandom MediaWiki (`Module:S2Localization`)** | `ru` | **100%** | Lua таблица | MediaWiki API | CC BY-SA 3.0 |
| **Fandom MediaWiki (`langlinks`)** | uk, pl, fr, de | **1–10%** (дыры) | Wikitext / JSON | MediaWiki API | CC BY-SA 3.0 |

---

## 4. Рекомендации для сборщика каталога (`tools/build_s2_catalog.py`)

1. **Немедленное улучшение для украинского языка (`uk`):**
   - Добавить в [build_s2_catalog.py](file:///home/dmytro/Projects/save-editor/tools/build_s2_catalog.py) подгрузку словаря из репозитория `Trasiankus/stalker2-bel/localization.json` (или сохранить выжимку `sid_*_name` в [data/s2_sources.json](file:///home/dmytro/Projects/save-editor/data/s2_sources.json)).
   - Это поднимет покрытие украинского языка с **141** до **1375+ предметов (100%)** без ручного труда.

2. **Стратегическое решение для всех 15 языков:**
   - Извлечь из Zone Kit (`Stalker2/Content/TextToolBackup/TextDatabase.json`) или распакованного `LocalizationDB.ubulk` только релевантные для инвентаря ключи (`sid_items_*_name`, `sid_questItemprototypes_*_name`, `sid_upgrades_*_name`);
   - Упаковать их в компактный файл `data/s2_item_names_multilang.json.gz` (~300–400 КБ);
   - Встроить обработку этого файла в [build_s2_catalog.py](file:///home/dmytro/Projects/save-editor/tools/build_s2_catalog.py). В результате интерфейс редактора на немецком, польском, французском, испанском, чешском, японском и других языках получит 100% аутентичные официальные имена GSC.
