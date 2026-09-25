# CS — Save Editor 2.0 на C# (side-by-side)

**Цель:** Save Editor 2.0 на C#. Python-версия служит только эталоном поведения и источником доказательств.

**Решение:** D5.

**Условия:**

- Windows, Linux и macOS — первоклассно.
- Avalonia UI.
- Чистое C#-ядро без UI.
- CLI.
- Никакого Python-рантайма.
- Детерминированные content packs.
- Явная модель capability и evidence.
- Фича не готова без L3 из собранного пакета.

**Роли.**

- Claude: архитектура, спецификации модулей, ревью каждого PR, решения по writer'ам.
- Codex: порт модуля за модулем по спецификации и golden-векторам до паритета.
- Codex не принимает архитектурных решений: если спецификации не хватает, он останавливается и спрашивает.

## CS-1 — Golden-векторы из Python-оракула

**Кто:** Claude (формат) → Codex (реализация) · **Размер:** M · **Зависит:** RL-5 · **Уровень:** L2

**Шаги.**

1. `tools/export_golden.py`: на каждый сейв выдаёт JSON разобранного состояния:
   - формат, релиз, версии;
   - деньги;
   - предметы: handle, type_key, SID/section, count, condition, placement, upgrades;
   - экипировка, персонаж, предупреждения, capabilities.
2. Мутационные векторы: `EditPlan` → ожидаемое состояние после повторного разбора → ожидаемый результат проверок безопасности. Байты не сравниваются: эквивалентная сериализация допустима.
3. Синтетические фикстуры → векторы коммитятся. Личный корпус → векторы только локально (каталог RL-5).

## CS-2 — Архитектура и каркас

**Кто:** Claude (спека) → Codex (каркас) · **Размер:** M · **Зависит:** D5, CS-1

**Спека** `ARCHITECTURE.md` в новом репо (`Dmitriy-DE/S.T.A.L.K.E.R.-Save-Editor-Next`, создаёт владелец):

- `StalkerSaveEditor.Core`: `Formats/{XRay,Stalker2,Enhanced}`, `Editing` (immutable `EditPlan`), `Catalogs`, `Localization`, `Backups`, `Validation`, `Models`, `Capabilities` (`CapabilityMaturity`, `FeatureCapability` с evidence и сборками игры).
- `StalkerSaveEditor.Desktop` (Avalonia, MVVM), `.Cli`, `.Steam` (тонкий P/Invoke к `steam_api`), `.Updater` (машина состояний: Checking → Downloading → Verifying → WaitingForPermission → Installing → Restarting → Completed / Failed, с реальным exit code), `.Tests`.
- `ISaveSource`: `LocalSaveSource`, `SteamCloudSaveSource`. Core ничего не знает о Steam и UI.
- CI: сборка и тесты на Windows, Linux и macOS с первого коммита.
- Выбор .NET: 10 LTS; Avalonia 11.x.

Каждый модуль Python помечен KEEP, REDESIGN или DROP; таблица в спеке.

## CS-3 — Кодеки

**Кто:** Codex · **Размер:** M · **Зависит:** CS-2

**Kraken:**

- нативная `ooz` (C++, тот же источник, что `tools/build_ooz_encoder.py`) собирается в CI под 3 ОС;
- доступ через P/Invoke;
- тест: распаковка и упаковка S2-фикстур байт в байт как у Python.

**X-Ray LZO:** managed-порт с тестами на фикстурах трилогии.

## CS-4 — Readers, модуль за модулем

**Кто:** Codex · **Размер:** L · **Зависит:** CS-3

**Порядок:**

1. X-Ray container;
2. ТЧ, ЧН, ЗП: actor и inventory;
3. каталоги;
4. S2: GVAS, таблицы имён, инвентарь;
5. имена и иконки из тех же JSON, что у Python.

**PR по модулю.** Тест паритета: C#-разбор == golden JSON по всем полям из CS-1.

## CS-5 — Writers по одной capability

**Кто:** Codex + Claude · **Размер:** L · **Зависит:** CS-4 · **Уровень:** L5

**Порядок:** X-Ray деньги → стаки → добавление → удаление → прочность → … → S2.

**Для каждой capability:**

- мутационный вектор проходит;
- C# повторно разбирает свой результат;
- проверки безопасности (CRC, round-trip, бэкап);
- L5 в игре — до того, как UI получит кнопку.

## CS-6 — Avalonia UI

**Кто:** Codex · **Размер:** L · **Зависит:** CS-4

Экраны как в текущей версии. Тема и шрифт переносятся, локали берутся из тех же `locales/*.json`.

## CS-7 — Steam, updater, пакеты

**Кто:** Codex · **Размер:** L · **Зависит:** CS-6 · **Уровень:** L4

**Пакеты:**

- `win-x64`: установщик и portable;
- `linux-x64`: `.deb` и tar;
- `osx-arm64` и `osx-x64`: `.app` / `.dmg`.

OTA с L4 на каждой ОС.

## CS-8 — Переключение

**Кто:** Claude + владелец · **Размер:** S

**Когда:** паритет readers, все writers текущей версии с L5, L4 на трёх ОС.

**Что делается:**

- новый репозиторий становится основным;
- Python-репозиторий уходит в legacy/oracle;
- OTA из Python-версии ставит C#-версию.
