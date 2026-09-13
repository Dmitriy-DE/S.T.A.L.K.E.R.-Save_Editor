# Состояние и пробелы — 2026-09-13

## Подтверждённая база

Исходники v0.3.0 EXPERIMENTAL импортированы без изменения runtime. Linux self-test и синтаксис проверяются отдельно в [evidence](evidence/BASELINE_2026-09-13.md). Денежные значения контрольных файлов: 48645, 58870, 56995; ранее изменённый D639: 900000. Это проверка распаковки/структур, не запуск игры.

В продукте уже есть Tkinter GUI и CLI. Общий UI-free `EditorService` связывает parser и safe writers для entry points. Qt shell принят через [PR #39](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/39), inventory search/filter и staged money/stack forms — через [PR #40](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/40). U07 принят через [PR #47](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/47) (merge `658fe77`): поверх shell добавлены тёмная Zone-тема, structured metadata/CRC badges, sidebar и snapshot-backed summary cards; новые runtime-зависимости не добавляются. U04 принят через [PR #41](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/41): immutable preview и local apply используют тот же service/storage, bytes до preview не меняются. U05 принят через [PR #42](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/42): backup/hash browser и restore в новую локальную копию. U06 принят через [PR #43](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/43): Qt Cloud tab с явным connect/list/analyze и verified/uncertain upload. Подтверждённого Windows-дистрибутива пока нет; B01 добавляет builder для Windows zip, Linux tar.gz и Debian package. S06 добавляет локально проверенную cloud transaction state machine, но end-to-end Steam/GFN при импорте не выполнялся. P03 добавляет обязательную GitHub Actions matrix для Linux/Windows и Python 3.11/3.12; код слит через [PR #37](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/37), но пять запусков завершились `startup_failure` до создания jobs, поэтому runner evidence ещё ожидается. Baseline с исходниками: `2291832`.

## Найдено чтением исходников, требует regression-тестов

Статусный список ниже сохраняет историю карточек и их evidence. Актуально на
2026-09-13: U06 принята PR #43, U07 принята PR #47, B01 принят по коду
PR #44, B02 ведёт текущую acceptance matrix; см. [`docs/evidence/BETA_ACCEPTANCE.md`](evidence/BETA_ACCEPTANCE.md)
и [UI design evidence](evidence/UI_DESIGN_2026-09-13.md).

S01 принята в `main` через [PR #29](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/29): переносимый synthetic fixture и 9 baseline-тестов добавлены; runtime не изменялся. S02 принята через [PR #30](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/30): immutable snapshot правок и запрет опасной комбинации raw + изменение длины inventory arrays подключены к общему apply-слою. S03 принята через [PR #31](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/31): единый безопасный local export подключён к Tk/CLI. S04 принята через [PR #32](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/32): parser coverage и read-only неизвестных записей подключены к GUI/CLI. S05 принята через [PR #33](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/33): worker lifecycle покрыт fake helper и bounded response handling. P01 принята через [PR #34](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/34): loader выбирает platform `pyooz==0.0.8`, Linux legacy fallback и явные ошибки unsupported target; Windows native smoke остаётся P03 evidence. P02 принята через [PR #35](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/35): единые Linux/Windows user-data paths, legacy read-only fallback, launchers и helper discovery; реальный Windows/Steam smoke ещё не проверен. S06 принята через [PR #36](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/36): cloud transaction с fresh SHA, recovery и verified/uncertain receipts; live Steam/GFN остаётся отдельным manual gate. P03 код принят через [PR #37](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/37), runner gate остаётся открытым после startup failure без jobs. U01 принята через [PR #38](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/38): общий UI-free service слой подключён к Tk/CLI и покрыт parity/injection tests. U02 принята локально через [PR #39](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/39): Qt shell, async local inspect и empty/error states; native startup/DPI evidence и P03 runner gate ещё впереди. U03 принята через [PR #40](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/40): inventory model/view, поиск/фильтры и staged money/stack counts без изменения bytes. U04 принята через [PR #41](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/41): immutable preview и local apply через service/storage. U05 принята через [PR #42](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/42): journal/hash browser и restore проверенной копии в новый путь. U06 принята через [PR #43](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/43): Qt Cloud tab с явным connect/list/analyze и verified/uncertain upload. B01 код принят через [PR #44](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/44); внешний Windows/runner gate ведётся в B02.

Привязки относятся к импортированному baseline. Это конкретные ограничения, не исчерпывающий аудит безопасности.

| ID | Сценарий и исходник | Что сделать |
|---|---|---|
| S02 | app.py:480 превращает relative raw-offset в абсолютный при staging; save_format.py:742 применяет raw после attach/detach, меняющих длину массивов в :546. Адрес после массива может указывать уже на другие байты. | Запретить совмещение raw с изменением длины до доказанной адресации; привязать план к исходному SHA. |
| S02 | app.py:143 отключает лишь четыре кнопки, а :557 читает staged-словари в фоне. Пользователь может менять правки после подтверждения. | Неизменяемый снимок правок до запуска worker. |
| S03 | cli.py:14–17 пишет прямо в output, допускает `-o` равный исходнику и перезапись существующей копии без backup. | Общий путь backup/atomic export для GUI/CLI, запрет same-path по умолчанию. |
| S03 | app.py:523 использует timestamp до секунды; :572–573 пишет backup/output через write_bytes. Повторное имя может совпасть, прерванная запись оставляет частичный output. | UUID/exclusive backup, временный файл рядом с output, fsync/replace, fresh SHA локального источника. |
| S04 | save_format.py:353 пропускает неоднозначно распознанные handles; :361 разрешает все неизвестные kind кроме 0/1/2 при count>1. Неполный разбор визуально выглядит полным. | Отчёт coverage, неизвестные записи read-only, явные eligibility-правила. |
| S05 | steam_cloud.py:127 берёт Lock → _ensure():93 → start():87 → request() снова берёт тот же Lock при рестарте. Таймаут :113 оставляет читателя, который может забрать следующий ответ. | Управляемый lifecycle, один reader, уничтожение сессии после timeout; не ограничиваться заменой Lock на RLock. |
| S06 | `editor/transactions.py` теперь выполняет WriteFile/sync/persist/read через helper; `is_persisted` остаётся client-side flag и не доказывает серверный snapshot. | Реальный tagged helper/Steam run и game/GFN reload; в коде различать verified и uncertain. |

## Чего не хватает редактору

| Область | Сейчас | Задачи |
|---|---|---|
| Надёжность | Ограниченный self-test на личном файле; P03 workflow запускает synthetic suite на четырёх runner комбинациях, пять запусков завершились startup_failure до jobs | S01–S06, P03 |
| Linux + Windows | P01 добавляет decoder, P02 — paths/launcher/helper; P03 workflow добавлен, реальная Windows CI ещё впереди | P03, B01–B02 |
| Удобный UI | Tk/CLI и Qt используют общий service; Zone shell, metadata badges, summary cards, inventory search/filter, staged money/stack, preview/apply, backup browser/restore и Cloud tab работают локально; native DPI/Steam smoke остаются отдельными gates | U06, U07, B01, B02 |
| Восстановление | U05 показывает journal/hash status и восстанавливает verified backup в новую копию; in-place replacement и cloud restore не реализованы | U05, U06 |
| Названия и каталог | Маленький seed SID, связи с save не доказаны | R01–R02 |
| Прочность | Поле не доказано | R03–R04 |
| Новые предметы/clone | Нет allocator/registry/prototype evidence | R05–R07 |
| Настоящее удаление | Только detach | R08 |
| Attachments/upgrades | Нет подтверждённой схемы | R09–R10 |
| Размер output | Полностью несжатые restart blocks, примерно 27 MB | R11 |

Count=1 остаётся read-only в текущем stack editor. Нельзя просто разрешить все count=1: оружие/броня/квестовые объекты требуют отдельных правил и evidence. Полная поддержка других кампаний/версий игры также не доказана: MONEY_ANCHOR привязан к изученным сейвам.

Ранний файл 5967 читает 22645, скриншот показывает 30145. Причина не установлена; эти данные не составляют достоверную пару. Synthetic fixtures проверяют код, а не универсальность формата.

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

Внешняя проверка runner всё ещё отсутствует: P03 пять раз завершился
`startup_failure` до создания jobs. Поэтому до реального Ubuntu/Windows build
и clean-machine smoke release gate B02 остаётся открытым, а cross-platform beta
не объявляется готовой.

Implementation B01 принят через [PR #44](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/44),
merge `3346167`. Текущий рабочий проход — B02: acceptance matrix находится в
[`docs/evidence/BETA_ACCEPTANCE.md`](evidence/BETA_ACCEPTANCE.md), release
остаётся `blocked` до Windows/runner/DPI evidence.
