# X-Ray container — M06 evidence

Исследование и локальная проверка выполнены 2026-09-15. Эта запись разделяет
публично известную схему контейнера и то, что реально принято для этого
проекта. Байты личных сейвов в репозиторий не добавлялись.

## Публичное исследование

- В открытом [stalker-tools `save_tool.py`](https://github.com/stalker-tools/tools/blob/main/save_tool.py)
  чтение начинается с трёх little-endian `u32`: `magic`, `version` и
  `unpacked_len`. Реализация принимает `magic == 0xffffffff`, отбрасывает
  версии ниже 2 и распаковывает оставшийся поток как raw LZO1X с ожидаемой
  длиной `unpacked_len`.
- В той же реализации после распаковки читаются little-endian chunk-записи
  `type,size`; среди известных типов есть ALIFE, SPAWN, OBJECT, GAME_TIME,
  REGISTRY и SCRIPT_VARS. Это полезное направление для дальнейшего чтения,
  но не доказательство расположения денег или инвентаря.
- В разборе [Valentin Pi формата SoC](https://github.com/valentinpi/valentinpi.github.io/blob/master/posts/soc/soc.md)
  показана запись внешнего заголовка `-1`, `ALIFE_VERSION`, исходный размер,
  затем raw LZO1X-1. Приведённый в статье образец имеет версию `0x0003`.
  Статья отдельно отмечает, что повторное сжатие может дать другие байты,
  хотя игра загрузила пересобранный файл. Поэтому «распаковать и снова сжать»
  не доказывает byte-for-byte round-trip.
- Публичный [xrWiki Save Unpacker](https://xray-engine.org/index.php?action=mpdf&title=S.T.A.L.K.E.R._save_unpacker)
  документирует unpack/repack-инструмент и историю поддержки SoC, CoP и CS.
  Это подтверждает наличие внешнего исследовательского материала, но не даёт
  SHA-доказательства для Enhanced Editions.
- Исходники [OpenXRay для SoC](https://github.com/ixray-team/ixray-1.0-stsoc),
  [CS](https://github.com/ixray-team/ixray-1.5-stcs) и
  [CoP](https://github.com/ixray-team/ixray-1.6-stcop) подтверждают сериализацию
  `GAME_TIME`, object registry, actor/trader money и ammo state. Таблица версий
  сверена с [Universal-ACDC](https://github.com/PSIget/Universal-ACDC): для
  современных релизов ожидаются spawn versions SoC 118, CS 122–124 и CoP 128.
- Для CoP быстрые сохранения используют отдельное расширение `.scop` согласно
  [документации OpenXRay](https://github.com/OpenXRay/xray-16/issues/1536).

## Что доступно локально

Репозиторный поиск по рабочему дереву по-прежнему не находит игровых файлов:

```text
rg --files -g '*.sav' -g '*.bak' -g '*.scop' .
```

Эти файлы намеренно остаются вне Git. Для локального read-only прогона найден
внешний установленный корпус оригинальных Steam-версий: 4 SoC `.sav`, 56 CS
`.sav` и 168 CoP `.scop`. Все 228 файлов распарсились с ожидаемой структурой
chunks `(ALIFE, GAME_TIME, SPAWN, OBJECT, REGISTRY)` и версиями контейнера
3/5/6; actor spawn versions — 118/124/128 соответственно. Это корпус
оригинальной трилогии на этой машине, а не доказательство всех модов,
патчей или Enhanced Editions.

## Решение

M06 разблокирована для подтверждённых оригинальных X-Ray контейнеров. Реализация
проверяет:

1. `magic=0xffffffff`, outer versions 3/5/6 и ожидаемый unpacked size;
2. raw LZO1X stream с bounds checks и строгой границей end marker;
3. little-endian chunks без обрезания, лишних байт и неизвестной внешней версии;
4. byte-for-byte no-op: `XRayContainer.build()` возвращает исходные bytes,
   если payload не менялся.

После изменения payload применяется безопасный literal-only LZO writer; его
compressed bytes не обещают совпадать с игрой. Поэтому no-op SHA является
отдельным доказательством, а игровой load/re-save остаётся внешним гейтом.

## Что ещё не принято

Для расширения заявления нужны отдельные данные:

- controlled pairs, где известны изменения денег и предметов;
- сохранения Enhanced Editions: [SoC EE discussion](https://steamcommunity.com/app/2427410/discussions/0/528723757459612258/)
  описывает отдельные `.sav/.dds/.info` в `Saved Games`, а [CS EE discussion](https://steamcommunity.com/app/2427420/discussions/0/603030907426702266/?l=ukrainian)
  сообщает об отличающемся `.scs`. Desktop discovery теперь показывает `.scs`
  как неизвестный кандидат вместо того, чтобы молча пропускать его; это не
  основание принимать его текущим X-Ray parser;
- загрузка отредактированной копии каждой оригинальной игры и повторное
  сохранение самой игрой.

До этих проверок не заявляются Enhanced Editions и полная совместимость с
модами. Неизвестные версии получают явный отказ.

## Локальный gate

Локальный gate после реализации:

```text
PYTHON=.venv/bin/python make check
PYTHON=.venv/bin/python make test
```

Зелёный gate не заменяет Windows runtime и проверку загрузкой игры.
