# X-Ray faction relations — 2026-09-15

Этот файл фиксирует read-only разбор отношений в официальных оригинальных
сейвах SoC, ЧН и ЗП. Моды, личные файлы и игровые эксперименты в Git не
попадают.

## Схема из исходников

В официальных исходниках [iXRay 1.0 SoC](https://github.com/ixray-team/ixray-1.0-stsoc),
[iXRay 1.5 Clear Sky](https://github.com/ixray-team/ixray-1.5-stcs) и
[iXRay 1.6 Call of Pripyat](https://github.com/ixray-team/ixray-1.6-stcop)
`RELATION_DATA::load/save` сериализует сначала personal map, затем map
отношений к communities. Для каждой записи используются `u32 count`, ключи
и signed `s32 goodwill`; ключом верхней map является object id персонажа.
Часть InfoPortions находится перед relation map в том же ALife registry chunk.
SoC/ЧН сохраняют у InfoPortion также `u64` timestamp, ЗП — только строку.

Редактор разбирает этот ограниченный префикс chunk 9, запоминает точные
границы и патчит только goodwill строки актёра. Если строки нет, она
добавляется в actor row в отсортированном порядке; остальные строки и хвост
registry сохраняются. Личные отношения не смешиваются с community goodwill.

Исходники задают пределы community goodwill:

| Игра | community goodwill | neutral threshold | friend threshold |
| --- | ---: | ---: | ---: |
| Shadow of Chornobyl | -3000…1000 | -400 | 500 |
| Clear Sky | -3000…1000 | -999 | 999 |
| Call of Pripyat | -3000…1000 | -999 | 999 |

При отсутствии community строки движок возвращает `NEUTRAL_GOODWILL` (0),
поэтому это значение показывается как `0 (default)`, а не как сохранённая
строка.

## Read-only probe на локальном корпусе

Использованы только копии установленных официальных сейвов; байты не
перезаписывались.

| Релиз | Actor community | Relation rows | Actor community offset |
| --- | ---: | ---: | ---: |
| Shadow of Chornobyl | 0 | 4 | 75731 |
| Clear Sky | 4 | 13 | 98779 |
| Call of Pripyat | 0 | 5 | 61831 |

Измеренные community rows: SoC `[(3, 0), (7, 0), (8, 200), (9, 50)]`, ЧН
содержит 13 строк с пределами от `-3000` до `1000`, ЗП — 5 строк, включая
`(1, -350)`, `(2, 1000)`, `(3, 1000)` и `(9, 1000)`. Эти значения являются
снимками конкретных сейвов, а не универсальным состоянием кампании.

## Реализация и граница записи

- `editor/xray_relations.py` имеет bounded parser/writer для InfoPortions,
  actor relation row, signed 32-bit bounds и сохранения хвоста.
- `SaveInfo` показывает только реально сохранённые community goodwill rows.
- Qt и web показывают faction catalog, текущие значения и конкретное
  предупреждение для ЧН/SoC/ЗП; staged UI не меняет исходный файл.
- `EditPlan.faction_relations` валидирует exact release-scoped keys; чужой или
  неизвестный numeric id отклоняется.
- Synthetic tests проверяют patch одной строки, добавление отсутствующей
  строки, сохранение personal/other rows и round-trip.

Запись в production UI для трёх оригинальных релизов включена как
`experimental_fields`: Qt/web показывают предупреждение, desktop backup
обязателен, browser скачивает новую копию без изменения источника. Controlled
game load/re-save по процедуре [M10](../tasks/M10.md) ещё не выполнялся.
Структурный round-trip доказывает сохранение контейнера и полей, но не
доказывает, что сюжет не перезапишет community или что внутриигровой AI
примет изменение.
