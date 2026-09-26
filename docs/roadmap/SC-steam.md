# SC — Steam: облако и достижения

## SC-1 — Честный статус записи в облако

**Кто:** Claude · **Размер:** S · **Уровень:** L4

**Найдено 2026-09-26.** Нативный writer сообщил «persisted», но сервер Steam правку не получил: файл остался в локальном `remote/`, а `remotecache.vdf` хранил оригинал. Вероятная причина — одновременная сессия игры на другом устройстве (GeForce Now), при которой Steam откладывает выгрузку.

**Шаги.**

1. После `wait_persisted`, если доступен веб-режим (CEF 8080), скачать файл с сервера и сверить SHA с выгрузкой. «Verified» ставится только при совпадении.
2. Если веб-режима нет, писать «записано локально, сервер не подтверждён» и объяснять, как проверить.
3. Перед записью проверить `remotecache.vdf` и признаки запущенной игры на другом устройстве. Предупредить: «закрой игру в GFN/на другом ПК».
4. Тест с подменой: persisted=True, сервер отдаёт старый SHA → статус `uncertain` с понятной причиной.

## SC-2 — Убрать SteamCloudFileManager helper

**Статус:** [PR #194](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/194) открыт, не смержен.

**Кто:** Codex · **Размер:** S · **Зависит:** SC-1

Нативный ctypes-воркер (`editor/steam_native.py`) обслуживает RemoteStorage, а локальная Steam CEF-страница через CDP остаётся web-путём для чтения списка и скачивания. Внешний helper, его выбор, распаковка AppImage, упаковочные метаданные и transport-тесты удалены. Steam Cloud writes остаются в native worker или защищённом S2 Auto-Cloud flow. Полные pytest (941 passed), Ruff, mypy и web bundle check проходят локально. [GitHub CI](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/36259731656) прошёл на Ubuntu и Windows, Python 3.11/3.12.

## SC-3 — Достижения Steam (как Steam Achievement Manager)

**Кто:** Claude (дизайн) → Codex · **Размер:** M · **Уровень:** L4

**Суть.** Вкладка «Достижения» для каждой игры с достижениями (S2, EE; у оригиналов в Steam достижений нет — проверить). Показать список, в том числе полученные. Разблокировать или сбросить выбранные.

**API.** Тот же нативный воркер от имени игры (`SteamAPI_Init` с AppID):

- `ISteamUserStats::RequestCurrentStats` / `RequestUserStats`;
- `GetNumAchievements`, `GetAchievementName`, `GetAchievement`, `GetAchievementDisplayAttribute` (name, desc, hidden), `GetAchievementIcon`;
- `SetAchievement` / `ClearAchievement` → `StoreStats`.

**Правила.**

- Действие явное: подтверждение со списком изменений.
- Запрещено, пока игра запущена.
- Проверка после `StoreStats` повторным чтением.
- Предупреждение, что сброс необратим для статистики.

**Приёмка.** L4 — владелец разблокирует одно достижение, Steam показывает его в профиле.
