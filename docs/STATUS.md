# Состояние и пробелы — 2026-09-13

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
| Надёжность | Матрица `tests` зелёная 4/4 (Linux и Windows × Python 3.11/3.12), lint и typecheck в каждой job, self-test на личном файле | — |
| Linux + Windows | Decoder, пути, launcher и helper на обеих ОС; CI зелёная на обеих; Windows `.exe` собран и его diagnostic пройден на runner. Не проверен запуск окна на живом Windows-десктопе | B02 |
| Удобный UI | Qt и CLI используют общий service; Zone shell, metadata badges, summary cards, inventory search/filter, staged money/stack, preview/apply, backup browser/restore и Cloud tab работают локально. U02–U07 приняты; открыт только native DPI/Steam smoke | B02 |
| Восстановление | U05 показывает journal/hash status и восстанавливает verified backup в новую копию; in-place replacement и cloud restore не реализованы | новая карточка (не заведена) |
| Названия и каталог | Маленький seed SID, связи с save не доказаны | R01–R02 |
| Прочность | Поле не доказано | R03–R04 |
| Новые предметы/clone | Нет allocator/registry/prototype evidence | R05–R07 |
| Настоящее удаление | Только detach | R08 |
| Attachments/upgrades | Нет подтверждённой схемы | R09–R10 |
| Размер output | Полностью несжатые restart blocks, примерно 27 MB | R11 |

Count=1 остаётся read-only в текущем stack editor. Нельзя просто разрешить все count=1: оружие/броня/квестовые объекты требуют отдельных правил и evidence. Полная поддержка других кампаний/версий игры также не доказана: MONEY_ANCHOR привязан к изученным сейвам.

Ранний файл 5967 читает 22645, скриншот показывает 30145. Причина не установлена; эти данные не составляют достоверную пару. Synthetic fixtures проверяют код, а не универсальность формата.

## Веб-версия

`web/` запускает то же ядро в браузере через Pyodide, нативная распаковка —
`ooz-wasm`. Сверка на реальном сейве: распаковка и обе правки дают те же
SHA-256, что десктоп ([evidence](evidence/WEB_EDITION_2026-09-14.md)).
Steam Cloud в вебе невозможен по устройству Steam, а не по нашей лени:
[разбор вариантов](evidence/STEAM_CLOUD_OPTIONS.md). Сайт опубликован: <https://stalker2-save-editor.pages.dev>,
обновление — `make web-deploy` (Cloudflare Pages). Проверено
живьём: страница, стили, ядро и мост отдаются, редактор открывает сейв.

## M01 — реестр форматов — 2026-09-15

На ветке `codex/m01-format-registry` реализован статический реестр форматов
([PR #48](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/48),
commit `559bb1a`). В нём зарегистрирован только `stalker2`; адаптер делегирует
существующим `save_format.inspect_save` и `editor.prepare.prepare_edit`.
`EditorService` выбирает формат по содержимому, а local/Cloud snapshots
передают ID и title формата. `make check` и `make test` прошли локально на
Linux (`165 passed`). M02 и X-Ray форматы ещё не реализованы; Windows,
игровая загрузка и shared/production deployment этим результатом не доказаны.

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
