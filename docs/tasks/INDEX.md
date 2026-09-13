# Очередь задач

Текущий результат — **U03 / issue #12**. S01–S06, P01 и P02, код P03, U01 и U02 приняты в `main`; P03 runner gate остаётся открытым после четырёх `startup_failure` запусков без jobs. U03 добавляет Qt-модель инвентаря, поиск, фильтры и staged stack edits без записи bytes; preview/apply остаётся U04. Все 28 issues созданы. `waiting_dependencies` означает, что входной gate ещё не принят, `in_progress` — ветка выполняется, `in_review` — PR открыт, `accepted` — PR слит и проверки записаны. Одна карточка — один PR.

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
| [P03](P03.md) | CI для Linux и Windows без личных сейвов | S01, S02, S03, S04, S05, S06, P01, P02 | in_progress (runner blocked) | [#9](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/9), [PR #37](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/37) |
| [U01](U01.md) | Общий service слой для GUI и CLI | S02, S03, S04, S06, P02 | accepted | [#10](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/10), [PR #38](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/38) |
| [U02](U02.md) | Qt shell и открытие локального сохранения | U01, P03 | accepted (local; P03/native gates pending) | [#11](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/11), [PR #39](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/39) |
| [U03](U03.md) | Инвентарь: поиск, фильтры и редактирование стаков | U02, S04 | in_progress | [#12](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/12) |
| [U04](U04.md) | Предпросмотр изменений и безопасный apply | U03 | waiting_dependencies | [#13](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/13) |
| [U05](U05.md) | Журнал backup и восстановление локальной копии | U04, S03 | waiting_dependencies | [#14](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/14) |
| [U06](U06.md) | Qt Steam Cloud и состояния синхронизации | U04, U05, S06 | waiting_dependencies | [#15](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/15) |
| [B01](B01.md) | Воспроизводимые standalone сборки | U06, P03 | waiting_dependencies | [#16](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/16) |
| [B02](B02.md) | Приёмка beta и GitHub prerelease | B01 | waiting_dependencies | [#17](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/issues/17) |
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

[Машиночитаемые карточки](tasks.json) содержат те же ID, зависимости и issue URLs. [ROADMAP](../plans/ROADMAP.md) задаёт порядок этапов; [спецификация](../specs/CROSS_PLATFORM_EDITOR.md) — общие контракты. Статус меняется только по фактически принятому результату.
