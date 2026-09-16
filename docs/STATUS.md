# Состояние и пробелы — 2026-09-15

## Актуальный official-release pass

После merge PR #53 текущая база `main` расширяет старый S2-only редактор одним
shared registry для официальных PC-профилей. Ветка M10 добавляет протокол
игровой проверки. Локальный parser/writer и UI расширены: source-backed поля
с round-trip могут быть доступны как experimental, но это не заменяет
controlled game load/re-save по M10. Личные игровые файлы автоматически не
перезаписываются:

| Profile | Registry status | Proven capability |
|---|---|---|
| S.T.A.L.K.E.R. 2 | зарегистрирован | container/inventory read; upgrades и mutation gate остаются read-only без локального образца и подтверждённой игровой схемы |
| Original Shadow of Chornobyl | зарегистрирован | X-Ray read; money/stack/catalog работают; condition, relations и player community доступны как source-backed experimental edits; старый STATE без upgrade vector |
| Original Clear Sky | зарегистрирован | X-Ray read; money/stack/catalog работают; condition, upgrades, relations и player community доступны как source-backed experimental edits |
| Original Call of Pripyat | зарегистрирован | X-Ray read; money/stack/catalog работают; condition, upgrades, relations и player community доступны как source-backed experimental edits |
| Shadow of Chornobyl EE | descriptor/path discovery only | unavailable; no accepted format sample |
| Clear Sky EE | descriptor/path discovery only | unavailable; no accepted format sample |
| Call of Pripyat EE | descriptor/path discovery only | unavailable; no accepted format sample |

Desktop использует release-specific auto/manual save discovery; одноимённые
Enhanced `.dds/.info` sidecars группируются с save-кандидатом и не открываются
отдельно. Browser остаётся local-file-only и content-detects файл тем же ядром.
Capability flags управляют Qt/web controls, а `experimental_fields` заставляет
обе оболочки показать предупреждение и backup policy. Это не доказывает, что
сюжет не перезапишет community или что игра примет condition/upgrade. Community
mods намеренно вне scope. X-Ray evidence:
[container](evidence/XRAY_CONTAINER.md), [inventory](evidence/XRAY_INVENTORY_2026-09-15.md),
[catalog](evidence/XRAY_CATALOG_2026-09-15.md), [faction catalog](evidence/XRAY_FACTION_CATALOG.md),
[relations](evidence/XRAY_FACTION_RELATIONS_2026-09-15.md),
[upgrades](evidence/XRAY_UPGRADES_2026-09-15.md),
[durability](evidence/XRAY_DURABILITY_2026-09-15.md),
[EE boundary](evidence/EE_FORMATS_2026-09-15.md).

Локальный Linux gate текущего прохода: `PYTHON=.venv/bin/python make check` exit 0,
`PYTHON=.venv/bin/python make test` exit 0 (`330 passed`); ruff,
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
| Восстановление | U05 сохраняет verified backup/journal и восстанавливает копию; M16 добавляет явную desktop in-place replacement и одношаговый откат исходного слота с safety backup | M16; cloud restore отсутствует по границе платформы |
| Названия и каталог | Resource-derived item/faction catalogs загружаются desktop/web; при отсутствии локальных официальных ресурсов desktop использует компактный проверенный metadata snapshot, а локальный atlas остаётся недоступен; SID semantics не доказана | M11, R01–R02 |
| Прочность | STATE condition читается для actor-owned weapon/outfit; source-backed writer и Qt/web staging доступны как experimental с явным backup warning | M12, R03–R04 |
| Новые предметы/clone | Для оригинальной трилогии работают catalog key + same-family registry template; S2 и неизвестные families запрещены | R05–R07 |
| Настоящее удаление | X-Ray deep removal actor-owned registry record; reference-safe/equipped deletion не доказано | R08 |
| Attachments/upgrades | X-Ray upgrade vector source-backed для ЧН/ЗП; attachments и S2 upgrades read-only | R09–R10 |
| Отношения и принадлежность | X-Ray relation registry и actor community читаются, Qt/web controls и bounded writer доступны как experimental с сюжетными предупреждениями; game semantics не подтверждены | M14–M15 |
| Размер output | X-Ray edit использует безопасный literal-only LZO writer; output может быть больше исходного | R11 |

Count=1 остаётся read-only в текущем stack editor. Нельзя просто разрешить все count=1: оружие/броня/квестовые объекты требуют отдельных правил и evidence. Полная поддержка других кампаний/версий игры также не доказана: MONEY_ANCHOR привязан к изученным сейвам.

Ранний файл 5967 читает 22645, скриншот показывает 30145. Причина не установлена; эти данные не составляют достоверную пару. Synthetic fixtures проверяют код, а не универсальность формата.

## Веб-версия

`web/` запускает то же multi-format ядро в браузере через Pyodide: `ooz-wasm`
для S.T.A.L.K.E.R. 2 и portable Python LZO для оригинальной трилогии. Веб
принимает файл локально, распознаёт только зарегистрированный формат и
отказывает на неизвестном. Для оригинальной трилогии condition snapshot и
staged durability проходят тот же bridge и доступны как experimental с
предупреждением о ручном backup. Для ЧН/ЗП staged upgrade vectors, relation rows
и player community проходят через тот же общий `EditPlan`/bridge-контракт;
production semantics остаются неподтверждёнными отдельным game evidence. S2 и
Enhanced остаются read-only до отдельного evidence. Сверка S2
остаётся в [evidence](evidence/WEB_EDITION_2026-09-14.md), X-Ray bridge
покрыт `tests/test_web_bridge.py`.
Steam Cloud в вебе невозможен по устройству Steam, а не по нашей лени:
[разбор вариантов](evidence/STEAM_CLOUD_OPTIONS.md). Сайт опубликован: <https://stalker2-save-editor.pages.dev>,
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
результаты не открывают UI/web mutation до M10. Move, equipment, прочность,
durability/upgrades, attachments и reference-safe deletion остаются read-only.
Enhanced Editions также не объявлены поддержанными: evidence записан отдельно
в `EE_FORMATS_2026-09-15.md`.

Локальный корпус подтверждает чтение и no-op SHA-preserving round-trip; game
load/re-save, Windows runtime и Enhanced остаются внешними gates. Базовая
реализация M01–M09 принята в `main` через PR #53; PR #54–#56 закрыты как
устаревшие дубликаты. Текущий проход M10–M16 ведётся отдельными карточками и
не должен смешиваться с историческим описанием M06–M09.

### Дополнительный read-only corpus probe — 2026-09-16

Повторная проверка установленной оригинальной трилогии прошла без изменения
файлов: ТЧ 6/6, ЧН 59/59, ЗП 171/171. Все найденные кандидаты распарсились,
`unresolved` равен нулю. Это расширяет локальную parser-проверку, но не
подтверждает загрузку или сохранение изменённого результата самой игрой.

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
