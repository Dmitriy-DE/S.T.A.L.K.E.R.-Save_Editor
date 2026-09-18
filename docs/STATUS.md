# Состояние и пробелы — 2026-09-16

## 2026-09-18 — v0.5.0: встроенное облако, автопоиск-подсказки, вёрстка

- **Steam Cloud внутри проекта.** Добавлен `editor/steam_native.py` —
  in-process worker на `ctypes` поверх `libsteam_api` (ISteamRemoteStorage):
  init/list/read/write/sync. `editor/steam_backend.py` выбирает native, а при
  неудаче молча откатывается на helper. Сторонний Rust-проект больше не
  обязателен. Живьём подтверждён `SteamAPI_Init + connect + list` для S2
  (app_id 1643320); `GetFiles` вернул 0 (сейвов в облаке не было), поэтому
  реальный read/write остаётся на пользовательской проверке.
- **Краш `libfuse.so.2` устранён.** Helper-fallback распаковывает AppImage
  через `--appimage-extract` (без FUSE) и запускает внутренний ELF; проверено
  локально (`Ping/Pong`).
- **Автопоиск-подсказки во всей апке.** Под полями Steam root / папка игры /
  папка сейвов показывается реально найденный путь (или «ничего не найдено»)
  для каждой игры; Clear Sky/SoC/CoP находятся, Steam root тоже.
- **«Неизвестно» → «—» с тултипом.** Инвентарные поля, которых формат не
  хранит, показываются как «—» с объяснением, а не пугающим «неизвестно».
- **Вёрстка.** Стековые вкладки обёрнуты в один предсказуемый скролл; убраны
  наезды/обрезка; карточки локация/время для S2 показывают «—» с GVAS-тултипом
  (схема UE5 GVAS по-прежнему не разбирается — это вне скоупа релиза).

## 2026-09-18 — опубликован v0.4.3

Тег `v0.4.2` оставлен неизменяемым, но GitHub Release для него не создавался:
Linux standalone job прошёл, а Windows source-test job завершился с
`0xC0000409` при завершении Qt worker. В `v0.4.3` добавлено ожидание
save-discovery worker при закрытии окна и регрессионный тест на этот сценарий;
standalone workflow #35350988272 прошёл на Linux и Windows, assets опубликованы
в [GitHub Release v0.4.3](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.4.3).

На ветке release-кандидата исправлены проблемы, видимые в старом бинарнике
`v0.4.0`:

- карточка денег больше не затирает найденное значение в `—`; S2 money можно
  застейджить и подготовить к preview как отдельное экспериментальное поле;
  stacks, неизвестные handles и остальные неподтверждённые мутации остаются
  read-only;
- S2 embedded save-local name table подключена к inventory presentation;
  неизвестное имя по-прежнему показывается честно вместе с type-key/handle;
- inventory получил приоритет широкой колонке имени, минимумы для технических
  колонок, горизонтальный скролл и двухстрочные action-группы вместо сжатой
  строки из четырёх кнопок;
- отсутствующие в текущем S2 parser location/time показываются как `не
  разобрано`, а не как пустая/выдуманная метрика;
- SteamCloudFileManager уже используется как внешний JSON worker adapter.
  Discovery находит распакованный Linux asset с соседней библиотекой,
  `Ping`/`Connect` прошли локально; `GetFiles` вернул 0, upload не выполнялся.

Парсер S2 money и его decompression/CRC/SHA/round-trip guards не являются
доказательством принятия изменённого файла игрой. Для этого нужен отдельный
load/re-save evidence row на конкретной версии S.T.A.L.K.E.R. 2.

## 2026-09-18 — Zone launcher и вход в Steam Cloud

Desktop теперь стартует с единой read-only библиотекой: все четыре семейства
официальных игр и найденные локальные `.sav`/`.scop` отображаются сразу,
выбор игры фильтрует список, а неизвестные файлы остаются видимыми с честным
статусом. `ИМПОРТ СЕЙВА…` открывает внешний файл через content-only detector и
не требует установленной игры.

На стартовом экране добавлена явная кнопка `STEAM CLOUD`, которая переводит в
существующий Qt Cloud flow без предварительного локального сейва: helper
подключается, перечисляет удалённые `S.T.A.L.K.E.R. 2` `Data/*.sav`, выбранный
слот скачивается и анализируется, а подготовленный preview можно отправить
обратно через fail-closed transaction с backup, fresh SHA, persisted-проверкой
и read-back SHA. Транспорт по-прежнему S.T.A.L.K.E.R. 2-only; оригинальная
трилогия/Enhanced Edition и live runtime без установленной игры требуют
отдельного evidence и здесь не объявляются подтверждёнными.

Локальная проверка этого прохода: `PYTHON=.venv/bin/python make check` — exit 0,
`PYTHON=.venv/bin/python make test` — exit 0 (`411 passed`); `make package-plan`
и Linux packaging выполняются отдельно на текущем host.

## Актуальный official-release pass

После merge PR #53 текущая база `main` расширяет старый S2-only редактор одним
shared registry для официальных PC-профилей. Ветка M10 добавляет протокол
игровой проверки. Владелец подтвердил загрузку и сохранение подготовленных
сейвов в локальных оригинальных SoC/CS/CoP, поэтому их mutation capabilities
открыты; независимый SHA parser read-back второго сохранения не собирался:

| Profile | Registry status | Proven capability |
|---|---|---|
| S.T.A.L.K.E.R. 2 | зарегистрирован | read, save-local inventory names, локальный money/stack parser и optional official CFG catalog; mutation capability и SID-based constructor ждут evidence |
| Original Shadow of Chornobyl | зарегистрирован | X-Ray read и локальный money/stack/catalog writer; UI/web mutation ждёт M10 |
| Original Clear Sky | зарегистрирован | X-Ray read и локальный money/stack/catalog writer; UI/web mutation ждёт M10 |
| Original Call of Pripyat | зарегистрирован | X-Ray read и локальный money/stack/catalog writer; UI/web mutation ждёт M10 |
| Shadow of Chornobyl EE | descriptor/path discovery only | unavailable; no accepted format sample |
| Clear Sky EE | descriptor/path discovery only | unavailable; no accepted format sample |
| Call of Pripyat EE | descriptor/path discovery only | unavailable; no accepted format sample |

Desktop использует release-specific auto/manual save discovery; browser остаётся
local-file-only и content-detects файл тем же ядром. Capability flags теперь
управляют Qt/web controls, а M10 gate не позволяет синтетическому round-trip
выглядеть как доказательство загрузки в игре. Community mods намеренно вне
scope. X-Ray evidence:
[container](evidence/XRAY_CONTAINER.md), [inventory](evidence/XRAY_INVENTORY_2026-09-15.md),
[catalog](evidence/XRAY_CATALOG_2026-09-15.md), [EE boundary](evidence/EE_FORMATS_2026-09-15.md).

Локальный Linux gate текущего прохода: `PYTHON=.venv/bin/python make check` exit 0,
`PYTHON=.venv/bin/python make test` exit 0 (`283 passed`); ruff,
mypy, generated web bundle/theme и `node --check web/app.js` проходят. Linux
`tar.gz`/`.deb` и packaged diagnostic также собраны и проверены; Cloudflare
Pages revision `4d833b6f` прочитан обратно с HTTP 200 после обновления каталога и
поиска Enhanced-путей.
Точные хэши и URL записаны в
[release evidence](evidence/RELEASE_2026-09-15.md). Это не заменяет Windows
runtime, живой game load/re-save, Steam/GFN или GitHub Pages.

## Подтверждённая база

Исходники v0.3.0 EXPERIMENTAL импортированы без изменения runtime. Linux self-test и синтаксис проверяются отдельно в [evidence](evidence/BASELINE_2026-09-13.md). Денежные значения контрольных файлов: 48645, 58870, 56995; ранее изменённый D639: 900000. Это проверка распаковки/структур, не запуск игры.

В продукте один Qt-интерфейс и CLI поверх общего UI-free `EditorService`; Tkinter-интерфейс удалён после достижения Qt parity. Qt shell принят через [PR #39](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/39), inventory search/filter и staged money/stack forms — через [PR #40](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/40). U07 принят через [PR #47](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/47) (merge `658fe77`): поверх shell добавлены тёмная Zone-тема, structured metadata/CRC badges, sidebar и snapshot-backed summary cards; новые runtime-зависимости не добавляются. U04 принят через [PR #41](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/41): immutable preview и local apply используют тот же service/storage, bytes до preview не меняются. U05 принят через [PR #42](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/42): backup/hash browser и restore в новую локальную копию. U06 принят через [PR #43](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/43): Qt Cloud tab с явным connect/list/analyze и verified/uncertain upload. Подтверждённого Windows-дистрибутива пока нет; B01 добавляет builder для Windows zip, Linux tar.gz и Debian package. S06 добавляет локально проверенную cloud transaction state machine, но end-to-end Steam/GFN при импорте не выполнялся. P03 добавляет обязательную GitHub Actions matrix для Linux/Windows и Python 3.11/3.12; код слит через [PR #37](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/37), но пять запусков завершились `startup_failure` до создания jobs, поэтому runner evidence ещё ожидается. Baseline с исходниками: `2291832`.

## Найденные при аудите исходников риски и их покрытие

Таблица ниже — исходные находки чтения кода и карточка, которая их закрыла.
Все перечисленные карточки (S02–S06) приняты; строки остаются, потому что они
фиксируют, *почему* существуют соответствующие проверки, и их нельзя снимать
без нового evidence. Приёмочные матрицы: [`BETA_ACCEPTANCE`](evidence/BETA_ACCEPTANCE.md)
и [UI design evidence](evidence/UI_DESIGN_2026-09-13.md).

История приёмки карточек (какой PR что принял) вынесена в
[журнал приёмки](history/ACCEPTANCE_LOG.md); актуальные статусы очереди —
в [tasks.json](tasks/tasks.json) и сгенерированной из него
[таблице](tasks/INDEX.md). Здесь остаётся только текущее состояние.

Привязки относятся к импортированному baseline. Это конкретные ограничения, не исчерпывающий аудит безопасности.

| ID | Сценарий и исходник | Что сделать |
|---|---|---|
| S02 | (удалённый app.py):480 превращает relative raw-offset в абсолютный при staging; save_format.py:742 применяет raw после attach/detach, меняющих длину массивов в :546. Адрес после массива может указывать уже на другие байты. | Запретить совмещение raw с изменением длины до доказанной адресации; привязать план к исходному SHA. |
| S02 | (удалённый app.py):143 отключает лишь четыре кнопки, а :557 читает staged-словари в фоне. Пользователь может менять правки после подтверждения. | Неизменяемый снимок правок до запуска worker. |
| S03 | cli.py:14–17 пишет прямо в output, допускает `-o` равный исходнику и перезапись существующей копии без backup. | Общий путь backup/atomic export для GUI/CLI, запрет same-path по умолчанию. |
| S03 | (удалённый app.py):523 использует timestamp до секунды; :572–573 пишет backup/output через write_bytes. Повторное имя может совпасть, прерванная запись оставляет частичный output. | UUID/exclusive backup, временный файл рядом с output, fsync/replace, fresh SHA локального источника. |
| S04 | save_format.py:353 пропускает неоднозначно распознанные handles; :361 разрешает все неизвестные kind кроме 0/1/2 при count>1. Неполный разбор визуально выглядит полным. | Отчёт coverage, неизвестные записи read-only, явные eligibility-правила. |
| S05 | steam_cloud.py:127 берёт Lock → _ensure():93 → start():87 → request() снова берёт тот же Lock при рестарте. Таймаут :113 оставляет читателя, который может забрать следующий ответ. | Управляемый lifecycle, один reader, уничтожение сессии после timeout; не ограничиваться заменой Lock на RLock. |
| S06 | `editor/transactions.py` теперь выполняет WriteFile/sync/persist/read через helper; `is_persisted` остаётся client-side flag и не доказывает серверный snapshot. | Реальный tagged helper/Steam run и game/GFN reload; в коде различать verified и uncertain. |

## Чего не хватает редактору

| Область | Сейчас | Задачи |
|---|---|---|
| Надёжность | Общий parser gate покрывает S.T.A.L.K.E.R. 2 и подтверждённые оригинальные X-Ray containers; полный release gate всё ещё требует Windows/runtime evidence | B02 |
| Linux + Windows | Decoder, пути, launcher и helper на обеих ОС; CI зелёная на обеих; Windows `.exe` собран и его diagnostic пройден на runner. Не проверен запуск окна на живом Windows-десктопе | B02 |
| Удобный UI | Qt и CLI используют общий service; Zone shell, metadata badges, summary cards, inventory search/filter, staged money/stack, preview/apply, backup browser/restore и Cloud tab работают локально. U02–U07 приняты; открыт только native DPI/Steam smoke | B02 |
| Восстановление | U05 показывает journal/hash status и восстанавливает verified backup в новую копию; in-place replacement и cloud restore не реализованы | новая карточка (не заведена) |
| Названия и каталог | Оригинальные metadata-каталоги загружаются desktop/web; S2 embedded save-local name table разрешает текущие inventory keys, loose official CFG catalog читается read-only; переносимый prototype SID/локализация не доказаны | R01–R02, M21, M25 |
| Прочность | Experimental condition read/write добавлен для подтверждённых X-Ray weapon/outfit anchors; game load/re-save не выполнен | R03–R04, M12 |
| Новые предметы/clone | Для оригинальной трилогии работают catalog key + same-family registry template; S2 и неизвестные families запрещены | R05–R07 |
| Позиция предмета | Experimental `SInvItemPlace` read/write для actor-owned original SoC/CS/CoP; неизвестный anchor read-only, game load/re-save не выполнен | M20 |
| Настоящее удаление | X-Ray deep removal и Qt/web staging блокируют известные direct dependents, explicit equipped и unresolved targets; полный reference graph и game load/re-save не доказаны | M23–M24, R08 |
| Attachments/upgrades | `m_upgrades` подтверждён структурно для CS/CoP и доступен experimental; X-Ray addon flags/config compatibility mapped read-only, controlled attach/detach и game read-back отсутствуют; SoC/S2/Enhanced остаются read-only | M17, R09–R10 |
| Размер output | X-Ray edit использует безопасный literal-only LZO writer; output может быть больше исходного | R11 |

Count=1 остаётся read-only в текущем stack editor. Нельзя просто разрешить все count=1: оружие/броня/квестовые объекты требуют отдельных правил и evidence. Полная поддержка других кампаний/версий игры также не доказана: MONEY_ANCHOR привязан к изученным сейвам.

Ранний файл 5967 читает 22645, скриншот показывает 30145. Причина не установлена; эти данные не составляют достоверную пару. Synthetic fixtures проверяют код, а не универсальность формата.

## Веб-версия

`web/` запускает то же multi-format ядро в браузере через Pyodide: `ooz-wasm`
для S.T.A.L.K.E.R. 2 и portable Python LZO для оригинальной трилогии. Веб
принимает файл локально, распознаёт только зарегистрированный формат и
отказывает на неизвестном; до M10 game load/re-save mutation controls остаются
read-only, хотя локальный writer и catalog round-trip продолжают проверяться
отдельно. Сверка S2
остаётся в [evidence](evidence/WEB_EDITION_2026-09-14.md), X-Ray bridge
покрыт `tests/test_web_bridge.py`.
Steam Cloud в вебе невозможен по устройству Steam, а не по нашей лени:
[разбор вариантов](evidence/STEAM_CLOUD_OPTIONS.md). Сайт опубликован: <https://stalker-save-editor.pages.dev>,
обновление — `make web-deploy` (Cloudflare Pages). Проверено
живьём: страница, стили, ядро, мост и metadata catalog отдаются с HTTP 200.

## M01 — реестр форматов — 2026-09-15

На ветке `codex/m01-format-registry` реализован статический реестр форматов
([PR #48](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/48),
commit `559bb1a`). В нём зарегистрирован только `stalker2`; адаптер делегирует
существующим `save_format.inspect_save` и `editor.prepare.prepare_edit`.
`EditorService` выбирает формат по содержимому, а local/Cloud snapshots
передают ID и title формата. `make check` и `make test` прошли локально на
Linux (`165 passed`). M02 и X-Ray форматы ещё не реализованы; Windows,
игровая загрузка и shared/production deployment этим результатом не доказаны.

## M02 — content-only detection — 2026-09-15

На ветке `codex/m02-format-detection` реализован общий отказ для неизвестного
формата ([PR #49](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/49),
commit `2e12375`). Core-сообщение включает имя файла, размер, причины отказа и
список поддержанных форматов и передаётся без повторной диагностики в CLI, Qt
и web bridge. Покрыты empty, truncated, мусорный бинарник, ELF-like чужой
бинарник и текстовый `.sav`; исходные байты не меняются. Полный Linux gate:
`make check` exit 0, `make test` exit 0 (`173 passed`). Реальные X-Ray сейвы,
Windows и игровая загрузка этим результатом не подтверждены.

## M03 — исследование и discovery путей — 2026-09-15

На ветке `codex/m03-save-locations` реализованы read-only поисковые функции в
`editor/platforms.py` ([PR #50](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/50),
commit `23a02a3`). `steam_roots` учитывает Windows registry/fallback и обычный,
legacy и Flatpak Linux; `steam_libraries` сам разбирает KeyValues
`libraryfolders.vdf`, пропуская битый root с warning; `installed_games`
проверяет appmanifest и каталог. `save_directories` включает четыре семейства,
S2 Steam/EOS/GOG/Microsoft Store, original `_appdata_`, Enhanced/Legends,
локализованные Documents, Proton prefix и `fsgame*.ltx` override.

Источниковые пути и пробелы evidence записаны в
[`SAVE_LOCATIONS.md`](evidence/SAVE_LOCATIONS.md). Synthetic tree покрывает
alternate library, malformed VDF, localized Documents, Proton, Microsoft Store
profile и отсутствие записи. `PYTHON=.venv/bin/python make check` — exit 0;
`PYTHON=.venv/bin/python make test` — exit 0 (`183 passed`). Реальные установки,
Windows/GOG/Proton runtime и игровая загрузка не проверялись; отдельная GOG
path row для Clear Sky/Call of Prypiat Enhanced upstream-источниками не дана и
не объявлена подтверждённой.

## M04 — выбор слота из найденной папки — 2026-09-15

На ветке `codex/m04-save-slots` добавлена асинхронная read-only вкладка
«Найденные сейвы» ([PR #51](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/51),
commit `dc094b4`). Она использует кандидатные пути M03, перечисляет `.sav`,
сортирует их по времени изменения от новых к старым и определяет формат только
через общий content detector. Неизвестные файлы остаются видимыми с честной
пометкой; явное открытие использует существующий путь `MainWindow` и общий
`FormatDetectionError`. Пустой список показывает все проверенные пути, ручной
выбор файла сохранён, автоматического открытия и записи в игровые каталоги нет.
`make check` и `make test` прошли локально на Linux (`187 passed`). Реальные
X-Ray сейвы, Windows/Proton runtime и игровая загрузка этим результатом не
подтверждены.

## M05 — ручные пути и их запоминание — 2026-09-15

На ветке `codex/m05-manual-paths` добавлены versioned локальные настройки
([PR #52](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/52),
commit `851a30c`). JSON хранится в `user_data_dir()/settings.json`, пишется
атомарно и не попадает в репозиторий. Qt-вкладка позволяет задать корень Steam,
папку игры и папку сохранений по каждой игре. Действующий ручной путь имеет
приоритет над автоматическим поиском; исчезнувший путь показывает сообщение и
возвращает auto-search, а битый/чужой JSON заменяется в памяти пустыми
настройками без падения. `make check` и `make test` прошли локально на Linux
(`197 passed`). Реальные Windows/GOG/Proton установки и игровой runtime этим
результатом не подтверждены.

## M06–M09 — оригинальная X-Ray трилогия — 2026-09-15

В [XRAY_CONTAINER](evidence/XRAY_CONTAINER.md) зафиксированы raw LZO1X,
внешний `magic/version/unpacked_len`, chunks и границы принятого корпуса.
Общий `editor/xray_save.py` добавляет SoC/CS/CoP через таблицу specs:

- SoC: outer 3, actor spawn 118, 4/4 локальных файлов;
- CS: outer 5, actor spawn 124 на локальном корпусе, 56/56 файлов;
- CoP: outer 6, actor spawn 128, 168/168 `.scop` файлов.

Qt, CLI и web используют один detector/reader. Автопоиск принимает `.sav`,
`.scop` и `.scs`-кандидаты, ручной picker и browser не ограничены расширением;
неизвестный формат получает явный отказ. На desktop поиск кеширует неизменившийся
size/mtime результат, а полный inspect всегда перечитывает bytes и SHA.

Локально реализованы и проверяются actor money и ammo stack count (STATE +
UPDATE), immutable `EditPlan`, source SHA, backup/atomic export и повторный
parse. Object windows и length-changing registry framing индексируются строго.
Для оригинальной трилогии catalog-backed writer добавляет предметы из
официального metadata-каталога через same-family registry template и удаляет
actor-owned record как deep operation; SoC/CS/CoP representative in-memory
прогон покрыл десять serializer families в каждом релизе. Эти локальные
До M10 эти базовые результаты не открывали UI/web mutation; Move, equipment, attachments
и reference-safe deletion остаются read-only. M12–M20 вынесли прочность,
отношения, player community, in-place replacement, X-Ray upgrades и placement
в отдельные stacked review-карточки; M17 (PR #65) и M20 (PR #68) структурно проверены,
но controlled game load/re-save для новых полей ещё не выполнялся.
Enhanced Editions также не объявлены поддержанными: evidence записан отдельно
в `EE_FORMATS_2026-09-15.md`.

Локальный корпус подтверждает чтение и no-op SHA-preserving round-trip; game
load/re-save, Windows runtime и Enhanced остаются внешними gates. Реализация и
регрессии находятся в текущем проходе ветки `codex/m06-xray-container`, а
исторические PR #53–#56 остаются открытыми документными карточками до
переноса соответствующих коммитов.

## Текущий проход B02

U07 оформил внедрение приложенного Stitch visual reference и принят merge
`658fe77` через PR #47. В runtime
перенесены только palette/layout hierarchy и bindings к реальному snapshot;
статические demo-значения и нерелевантный Figma Make music-проект исключены.
Два новых regression-теста и полный Qt suite проходят локально; provenance и
граница импорта записаны в [UI design evidence](evidence/UI_DESIGN_2026-09-13.md).

B01 добавляет воспроизводимый PyInstaller onedir builder. Целевые результаты:
Linux x86_64 portable `tar.gz` и Debian/Ubuntu `.deb`, Windows x64 `zip` с
`SaveEditor.exe`; runtime Python, Qt и native decoder должны лежать внутри
bundle. Исходный core остаётся stdlib-only, `pytest` не попадает в runtime.

В текущем M18-проходе Support project добавлен как локальный Qt `QDialog` и
web modal с clipboard-only Copy/Copied feedback. Платёжные APIs, backend,
tracking, QR и startup/recurring popups не добавлялись; визуальная адаптация
X-Ray reference записана в [UI support evidence](evidence/UI_SUPPORT_2026-09-16.md).

В M19 к Qt-инвентарю подключены release-scoped X-Ray icon coordinates и
официальный `ui_icon_equipment.dds` resolver: atlas читается только из выбранной
официальной установки и кэшируется в памяти. Web остаётся local-file-only, не
получает игровые ассеты и показывает доступный категорийный glyph; известные
координаты official atlas остаются в tooltip. При недоступном atlas обе витрины
используют честный fallback, без копирования `.dds` или шрифтов в репозиторий.
Подробности: [M19](tasks/M19.md).

В M20 добавлены source-backed `SInvItemPlace` read/write и staging переноса
actor-owned предметов между слотами, поясом и рюкзаком для оригинальных
SoC/CS/CoP. Все три локальных корпуса разбираются без ошибок; exact anchor и
round-trip проходят, но M10 game load/re-save нового place ещё не выполнялся.
Подробности: [M20](tasks/M20.md) и [XRAY placement evidence](evidence/XRAY_PLACEMENT_2026-09-16.md).

В M21 добавлен read-only reader official S2 prototype CFG: точные SID,
категории, вес, max stack, equipment slot и upgrade SID; он подключён к
desktop source discovery и shared browser bundle contract. S2 compact
`type_key` пока не связан с prototype SID, поэтому add/clone/upgrade writer не
открыт. S2 не установлен на текущем хосте, статический `web/catalogs.json` не
расширялся догадочными данными. Подробности: [M21](tasks/M21.md) и [S2 catalog
evidence](evidence/S2_CATALOG_2026-09-16.md).

В M22 появился воспроизводимый read-only анализ нескольких S2 сейвов. На
доступном corpus есть 34 общих handle; у 13 меняется compact `type_key`, а
`052000` встречается у двух разных handle. В M25 добавлено чтение embedded
save-local name table: все parsed inventory rows доступных четырёх S2 samples
получили наблюдаемое имя (`25/25`, `36/36`, `34/34`, `34/34`). Это не
подтверждает переносимый SID-based constructor и не открывает S2 Add/clone/
upgrade writer, но UI больше не скрывает уже сериализованные имена за
`Неизвестный объект`. Подробности: [M22](tasks/M22.md) и [S2 mapping
evidence](evidence/S2_MAPPING_2026-09-16.md).

В M23 structural X-Ray `deep detach` получил read-only preflight по известным
`object_id`/`parent_id` edges: actor-owned leaf можно удалить, а explicit
equipped, direct dependent и unresolved target блокируются до записи. Полный
opaque reference graph и game load/re-save не заявляются. Подробности:
[M23](tasks/M23.md) и [X-Ray delete evidence](evidence/XRAY_DELETE_2026-09-16.md).

В M24 тот же decision появился per-item в общем snapshot: Qt и web отключают
удаление до staging и показывают причину blocker, а generated browser bundle
включает новый модуль. Batch-анализ parent map не делает snapshot квадратичным.
Подробности: [M24](tasks/M24.md) и [X-Ray delete UI evidence](evidence/XRAY_DELETE_UI_2026-09-16.md).

Actions включены. Матрица `tests` зелёная на Linux и Windows, `standalone-build`
собирает обе цели, packaged diagnostic проходит на самом Windows-раннере.
Разбор всех находок: [CI_AND_WINDOWS](evidence/CI_AND_WINDOWS_2026-09-14.md).
Остался единственный блокирующий гейт, который машина выполнить не может:
запустить `SaveEditor.exe` на живом Windows-десктопе и проверить окно, масштаб
и клавиатуру.

Implementation B01 принят через [PR #44](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/44),
merge `3346167`. Текущий рабочий проход — B02: acceptance matrix находится в
[`docs/evidence/BETA_ACCEPTANCE.md`](evidence/BETA_ACCEPTANCE.md), release
остаётся `blocked` до Windows/runner/DPI evidence.
