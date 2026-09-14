# Cross-platform Save Editor Implementation Plan

> **For agentic workers:** выполнять последовательно по одной карточке. При наличии навыков использовать superpowers:executing-plans; делегирование не требуется и не разрешено автоматически. Владелец выбрал GPT-5.6 Luna.

**Goal:** превратить импортированную v0.3 в удобный, проверяемый Linux/Windows редактор и отдельно довести исследовательские операции до подтверждённых возможностей.

**Architecture:** общее Python-ядро, immutable edit requests и единая безопасная запись для CLI и Qt; веб-поставка (этап 7) переиспользует то же ядро в браузере, а не повторяет его. Единственный desktop UI на PySide6, нативные decoder/helper для каждой ОС. Новые поля save добавляются через evidence gates. Runtime core держится на стандартной библиотеке; внешние decoder/UI зависимости pinned и вкладываются в воспроизводимые сборки.

**Tech Stack:** Python 3.11/3.12, pyooz 0.0.8, PySide6, pytest/pytest-qt, PyInstaller, `dpkg-deb`, GitHub Actions.

**Spec:** [CROSS_PLATFORM_EDITOR](../specs/CROSS_PLATFORM_EDITOR.md).

## Global constraints

- Целевые платформы первой beta: Windows 11 x64 и Ubuntu 22.04/24.04 x86_64.
- Python разработки: 3.11 и 3.12; первоначальная binary build lane — 3.11.
- Новые возможности не считаются сделанными из-за наличия этого плана. Версия поднимается по фактически принятому результату; текущая — 0.4.0 (импортированный baseline был 0.3.0-experimental).
- Не удалять backup/CRC/round-trip/fresh SHA/persisted/read-back. Не угадывать offsets/SID/allocator.
- CI synthetic-only; реальный Steam upload и игровой опыт требуют отдельного поручения.
- Одна карточка = одна ветка = один PR; не мержить и не пушить main автоматически.
- Бинарники не хранятся в дереве: публикуются через GitHub Releases после gates.

## Этапы

| Этап | Карточки | Результат и gate |
|---|---|---|
| 0 — импорт | выполнено | Исходники в корне, локальные originals сохранены вне Git |
| 1 — надёжность | S01→S02→S03→S04→S05→S06 | Synthetic regressions, immutable edits, безопасный export, явный coverage, bounded worker, uncertain cloud states |
| 2 — платформы | P01→P02→P03 | Native decoder/paths/launchers и реальная зелёная Linux/Windows CI matrix |
| 3 — удобство | U01→U02→U03→U04→U05→U06→U07→U08 | Общий service; Qt local/inventory/preview/backup/cloud, Zone UI shell и обзор с метаданными; Tk удалён по достижении parity |
| 4 — выпуск | B01→B02 | Windows `.exe`, Debian/Ubuntu `.deb` и portable Linux archive, checksums, local acceptance; cloud claim отдельно по evidence |
| 5 — исследование | R01→R02→R03→R04→R05→R06→R07→R08→R09→R10 | Evidence-gated names/durability/registry/clone/add/delete/attachments |
| 6 — размер файлов | R11 | Optional compact mode только при доказанном decoder round-trip и fallback |
| 7 — веб | W01→W02→W03 | Тот же parser в браузере (Pyodide + WASM-декодер), локальные файлы без сервера, публикация на Pages |

| 8 — несколько игр | M01→M02→M03→M04→M05, затем M06→M07→M08→M09 | Четыре игры серии: реестр форматов, определение по содержимому, поиск сейвов для всех изданий, выбор слота; X-Ray-контейнер, чтение CoP/CS/SoC и правки по evidence. [План](MULTI_GAME.md) |

Стрелки в таблице задают удобный последовательный порядок для одного исполнителя. Точные зависимости находятся в карточках и tasks.json. R01 может идти после S01, а R11 после P01; они не являются обязательными для local beta. Если research gate не пройден, независимые готовые карточки остаются доступными. Полный перечень функций не сокращён: непроверенные функции остаются в очереди, не выдаются за готовые.

## Начать с S01

[Список всех задач](../tasks/INDEX.md) — каноническая очередь и GitHub ссылки. Файлы карточек являются детализацией этого плана. Каждая содержит scope, dependencies, input/output contract, конкретные negative/positive scenarios и команду проверки.

Нельзя одной задачей «сделать всё на Windows», «переделать весь UI» или «дореверсить inventory». Если scope карточки вырос до нескольких независимо принимаемых результатов, оформить подзадачи с собственными test gates до реализации, не выполнять большой rewrite.

## Definition of done

Кодовая карточка: regression/positive tests + соответствующая platform check, документация поведения, reviewable PR и честные ограничения. Research: воспроизводимые hashes/known values/candidates/exclusions/applicability; если доказательств нет, статус blocked, dependent implementation закрыта. Release: exact artifact hashes + OS matrix + source tag, не только успешный build log.

Оценку длительности реверс-инжиниринга до получения corpus не давать: доступность контролируемых сохранений определяет критический путь. Цель первого usable beta — переносимость, безопасные money/stack edits и UI; Add/Clone/Delete остаются частью полного плана, но не задерживают проверенную local beta.
