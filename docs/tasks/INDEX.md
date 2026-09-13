# Очередь задач

Начать с S01. Одна карточка — один PR. Все функции пока planned; ready означает, что можно начать, а не что выполнено. Точные критерии находятся в карточках.

| ID | Задача | Зависимости | Статус |
|---|---|---|---|
| [S01](S01.md) | Переносимые fixtures и baseline-тесты | — | ready |
| [S02](S02.md) | Неизменяемый план правок и запрет опасного raw batch | S01 | waiting_dependencies |
| [S03](S03.md) | Единая безопасная локальная запись для GUI и CLI | S02 | waiting_dependencies |
| [S04](S04.md) | Полнота разбора и read-only неизвестных записей | S01 | waiting_dependencies |
| [S05](S05.md) | Steam worker: restart, timeout и единственный reader | S01 | waiting_dependencies |
| [S06](S06.md) | Cloud transaction и честное uncertain-состояние | S02, S03, S05 | waiting_dependencies |
| [P01](P01.md) | Decoder loader для Linux и Windows | S01 | waiting_dependencies |
| [P02](P02.md) | Пути данных, launcher и helper на обеих ОС | P01, S05 | waiting_dependencies |
| [P03](P03.md) | CI для Linux и Windows без личных сейвов | S01, S02, S03, S04, S05, S06, P01, P02 | waiting_dependencies |
| [U01](U01.md) | Общий service слой для GUI и CLI | S02, S03, S04, S06, P02 | waiting_dependencies |
| [U02](U02.md) | Qt shell и открытие локального сохранения | U01, P03 | waiting_dependencies |
| [U03](U03.md) | Инвентарь: поиск, фильтры и редактирование стаков | U02, S04 | waiting_dependencies |
| [U04](U04.md) | Предпросмотр изменений и безопасный apply | U03 | waiting_dependencies |
| [U05](U05.md) | Журнал backup и восстановление локальной копии | U04, S03 | waiting_dependencies |
| [U06](U06.md) | Qt Steam Cloud и состояния синхронизации | U04, U05, S06 | waiting_dependencies |
| [B01](B01.md) | Воспроизводимые standalone сборки | U06, P03 | waiting_dependencies |
| [B02](B02.md) | Приёмка beta и GitHub prerelease | B01 | waiting_dependencies |
| [R01](R01.md) | Контролируемый corpus и формат evidence | S01 | waiting_dependencies |
| [R02](R02.md) | Каталог SID отдельно от доказанного save mapping | R01 | waiting_dependencies |
| [R03](R03.md) | Найти и доказать поле прочности | R01 | waiting_dependencies |
| [R04](R04.md) | Редактирование подтверждённой прочности | R03, U04 | waiting_dependencies |
| [R05](R05.md) | Реестр объектов, allocator и prototype references | R01, R02 | waiting_dependencies |
| [R06](R06.md) | Клонирование одного подтверждённого типа предмета | R05, U04 | waiting_dependencies |
| [R07](R07.md) | Добавление предмета по подтверждённому SID | R02, R06 | waiting_dependencies |
| [R08](R08.md) | Настоящее удаление с анализом ссылок | R05, U04 | waiting_dependencies |
| [R09](R09.md) | Исследование attachments и upgrades | R01, R05 | waiting_dependencies |
| [R10](R10.md) | Редактирование доказанных attachments/upgrades | R09, U04 | waiting_dependencies |
| [R11](R11.md) | Компактная пересборка Kraken с безопасным fallback | S01, P01 | waiting_dependencies |

[Машиночитаемые карточки](tasks.json) содержат те же ID и зависимости. Спецификация: [Linux/Windows](../specs/CROSS_PLATFORM_EDITOR.md).
