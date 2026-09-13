# Состояние и пробелы — 2026-09-13

## Подтверждённая база

Исходники v0.3.0 EXPERIMENTAL импортированы без изменения runtime. Linux self-test и синтаксис проверяются отдельно в [evidence](evidence/BASELINE_2026-09-13.md). Денежные значения контрольных файлов: 48645, 58870, 56995; ранее изменённый D639: 900000. Это проверка распаковки/структур, не запуск игры.

В продукте уже есть Tkinter GUI и CLI. Отсутствует подтверждённый Windows-дистрибутив. S06 добавляет локально проверенную cloud transaction state machine, но end-to-end Steam/GFN при импорте не выполнялся. Baseline с исходниками: `2291832`.

## Найдено чтением исходников, требует regression-тестов

S01 принята в `main` через [PR #29](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/29): переносимый synthetic fixture и 9 baseline-тестов добавлены; runtime не изменялся. S02 принята через [PR #30](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/30): immutable snapshot правок и запрет опасной комбинации raw + изменение длины inventory arrays подключены к общему apply-слою. S03 принята через [PR #31](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/31): единый безопасный local export подключён к Tk/CLI. S04 принята через [PR #32](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/32): parser coverage и read-only неизвестных записей подключены к GUI/CLI. S05 принята через [PR #33](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/33): worker lifecycle покрыт fake helper и bounded response handling. P01 принята через [PR #34](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/34): loader выбирает platform `pyooz==0.0.8`, Linux legacy fallback и явные ошибки unsupported target; Windows native smoke остаётся P03 evidence. P02 принята через [PR #35](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/35): единые Linux/Windows user-data paths, legacy read-only fallback, launchers и helper discovery; реальный Windows/Steam smoke ещё не проверен. S06 в review: cloud transaction с fresh SHA, recovery и verified/uncertain receipts; live Steam/GFN остаётся отдельным manual gate.

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
| Надёжность | Ограниченный self-test на личном файле, нет CI с переносимыми fixtures | S01–S06 |
| Linux + Windows | P01 добавляет decoder, P02 — paths/launcher/helper; реальная Windows CI ещё впереди | P03, B01–B02 |
| Удобный UI | Технические таблицы, handles/type-key, экспериментальная лаборатория | U01–U06 |
| Восстановление | Файлы backup без полноценного журнала/restore flow | S03, U05 |
| Названия и каталог | Маленький seed SID, связи с save не доказаны | R01–R02 |
| Прочность | Поле не доказано | R03–R04 |
| Новые предметы/clone | Нет allocator/registry/prototype evidence | R05–R07 |
| Настоящее удаление | Только detach | R08 |
| Attachments/upgrades | Нет подтверждённой схемы | R09–R10 |
| Размер output | Полностью несжатые restart blocks, примерно 27 MB | R11 |

Count=1 остаётся read-only в текущем stack editor. Нельзя просто разрешить все count=1: оружие/броня/квестовые объекты требуют отдельных правил и evidence. Полная поддержка других кампаний/версий игры также не доказана: MONEY_ANCHOR привязан к изученным сейвам.

Ранний файл 5967 читает 22645, скриншот показывает 30145. Причина не установлена; эти данные не составляют достоверную пару. Synthetic fixtures проверяют код, а не универсальность формата.
