# Очередь задач

Текущий результат — **U07 принят через PR #47**, параллельно остаётся открытым **B02 / issue #17**. S01–S06, P01 и P02, код P03, U01–U07 приняты в `main`; B01 code принят через PR #44 и дал локальный Linux bundle, но Windows/runner gate ещё открыт. U07 добавляет визуальный Zone shell поверх существующего Qt workflow; B02 по-прежнему ведёт acceptance matrix и release decision. P03 runner gate остаётся открытым после startup failure запусков без jobs. До Windows/DPI/clean-machine evidence cross-platform beta остаётся `in_progress`. `ready` означает, что блокеров нет и карточку можно брать, `waiting_dependencies` — входной gate ещё не принят, `in_progress` — ветка выполняется, `in_review` — PR открыт, `accepted` — PR слит и проверки записаны. Все 29 проектных issues отражены в карточках. Одна карточка — один PR.

<!-- BEGIN GENERATED TASK TABLE -->

| ID | Задача | Зависимости | Статус | GitHub |
|---|---|---|---|---|
| [S01](S01.md) | Переносимые fixtures и baseline-тесты | — | accepted | [#1](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/1), [PR #29](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/29) |
| [S02](S02.md) | Неизменяемый план правок и запрет опасного raw batch | S01 | accepted | [#2](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/2), [PR #30](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/30) |
| [S03](S03.md) | Единая безопасная локальная запись для GUI и CLI | S02 | accepted | [#3](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/3), [PR #31](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/31) |
| [S04](S04.md) | Полнота разбора и read-only неизвестных записей | S01 | accepted | [#4](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/4), [PR #32](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/32) |
| [S05](S05.md) | Steam worker: restart, timeout и единственный reader | S01 | accepted | [#5](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/5), [PR #33](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/33) |
| [S06](S06.md) | Cloud transaction и честное uncertain-состояние | S02, S03, S05 | accepted | [#6](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/6), [PR #36](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/36) |
| [P01](P01.md) | Decoder loader для Linux и Windows | S01 | accepted | [#7](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/7), [PR #34](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/34) |
| [P02](P02.md) | Пути данных, launcher и helper на обеих ОС | P01, S05 | accepted | [#8](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/8), [PR #35](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/35) |
| [P03](P03.md) | CI для Linux и Windows без личных сейвов | S01, S02, S03, S04, S05, S06, P01, P02 | accepted (4/4 зелёных, Linux и Windows) | [#9](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/9), [PR #37](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/37) |
| [U01](U01.md) | Общий service слой для GUI и CLI | S02, S03, S04, S06, P02 | accepted | [#10](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/10), [PR #38](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/38) |
| [U02](U02.md) | Qt shell и открытие локального сохранения | U01, P03 | accepted (local; P03/native gates pending) | [#11](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/11), [PR #39](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/39) |
| [U03](U03.md) | Инвентарь: поиск, фильтры и редактирование стаков | U02, S04 | accepted | [#12](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/12), [PR #40](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/40) |
| [U04](U04.md) | Предпросмотр изменений и безопасный apply | U03 | accepted (PR #41) | [#13](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/13), [PR #41](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/41) |
| [U05](U05.md) | Журнал backup и восстановление локальной копии | U04, S03 | accepted (PR #42) | [#14](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/14), [PR #42](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/42) |
| [U06](U06.md) | Qt Steam Cloud и состояния синхронизации | U04, U05, S06 | accepted (PR #43) | [#15](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/15), [PR #43](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/43) |
| [U07](U07.md) | Интеграция Zone UI shell и темы из утверждённого макета | U06 | accepted (PR #47) | [#46](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/46), [PR #47](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/47) |
| [U08](U08.md) | Обзор: метаданные контейнера, читаемая сводка и счётчики разделов | U07 | in_review | — |
| [B01](B01.md) | Воспроизводимые standalone сборки | U06, P03 | accepted (Windows сборка и smoke пройдены на runner) | [#16](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/16), [PR #44](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/44) |
| [B02](B02.md) | Приёмка beta и GitHub prerelease | B01 | in_review (черновик prerelease v0.4.0 собран) | [#17](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/17) |
| [R01](R01.md) | Контролируемый corpus и формат evidence | S01 | waiting_dependencies | [#18](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/18) |
| [R02](R02.md) | Каталог SID отдельно от доказанного save mapping | R01 | waiting_dependencies | [#19](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/19) |
| [R03](R03.md) | Найти и доказать поле прочности | R01 | waiting_dependencies | [#20](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/20) |
| [R04](R04.md) | Редактирование подтверждённой прочности | R03, U04 | waiting_dependencies | [#21](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/21) |
| [R05](R05.md) | Реестр объектов, allocator и prototype references | R01, R02 | waiting_dependencies | [#22](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/22) |
| [R06](R06.md) | Клонирование одного подтверждённого типа предмета | R05, U04 | waiting_dependencies | [#23](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/23) |
| [R07](R07.md) | Добавление предмета по подтверждённому SID | R02, R06 | waiting_dependencies | [#24](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/24) |
| [R08](R08.md) | Настоящее удаление с анализом ссылок | R05, U04 | waiting_dependencies | [#25](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/25) |
| [R09](R09.md) | Исследование attachments и upgrades | R01, R05 | waiting_dependencies | [#26](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/26) |
| [R10](R10.md) | Редактирование доказанных attachments/upgrades | R09, U04 | waiting_dependencies | [#27](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/27) |
| [R11](R11.md) | Компактная пересборка Kraken с безопасным fallback | S01, P01 | waiting_dependencies | [#28](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/28) |
| [W01](W01.md) | Спайк: доказать, что ядро работает в браузере | — | accepted (ooz-wasm, сверка байт в байт) | — |
| [W02](W02.md) | Веб-интерфейс поверх общего ядра | W01 | accepted (локальные файлы, без сервера) | — |
| [W03](W03.md) | Публикация веб-версии | W02 | accepted (Cloudflare, живой URL) | — |
| [M01](M01.md) | Реестр форматов сохранений | — | ready | — |
| [M02](M02.md) | Определение игры по файлу и честный отказ | M01 | waiting_dependencies | — |
| [M03](M03.md) | Поиск Steam и папок сохранений | M01 | waiting_dependencies | — |
| [M04](M04.md) | Выбор слота из найденной папки | M03, M02 | waiting_dependencies | — |
| [M05](M05.md) | Ручные пути и их запоминание | M04 | waiting_dependencies | — |
| [M06](M06.md) | Corpus и формат evidence для чужого формата | M01 | waiting_dependencies | — |
| [M07](M07.md) | Первый парсер X-Ray: только чтение | M06 | waiting_dependencies | — |

<!-- END GENERATED TASK TABLE -->

Таблица выше генерируется из [tasks.json](tasks.json) командой
`python3 tools/render_task_index.py` (и проверяется `--check` в `make check` и в
тестах). Правится tasks.json, не таблица. [ROADMAP](../plans/ROADMAP.md) задаёт порядок этапов; [спецификация](../specs/CROSS_PLATFORM_EDITOR.md) — общие контракты. Статус меняется только по фактически принятому результату.
