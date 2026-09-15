# X-Ray faction catalog — 2026-09-15

Этот документ фиксирует только метаданные, извлечённые read-only из
официальных ресурсов. Сейвы, игровые архивы, личные пути и содержимое
локализаций в Git не попадают. Моды намеренно не используются.

## Источник и правило выбора

Для каждой оригинальной игры `XRayCatalogProvider` выбирает только ресурсный
корень этой игры. В распакованном `gamedata` overlay с очевидным маркером
community-мода отклоняется; затем проверяются официальные упакованные
архивы. Секция `[game_relations]` задаёт пары `community key → numeric id`, а
`[communities_relations]` задаёт матрицу значений. Отображаемое имя берётся
только из найденной локализации выбранного ресурса; отсутствующее имя
остаётся `None`.

Публичная исходная семантика X-Ray также видна в [OpenXRay
`script_game_object.h`](https://github.com/OpenXRay/xray-16/blob/dev/src/xrGame/script_game_object.h),
а release-specific исходники доступны в [iXRay 1.0 SoC](https://github.com/ixray-team/ixray-1.0-stsoc),
[iXRay 1.5 Clear Sky](https://github.com/ixray-team/ixray-1.5-stcs) и
[iXRay 1.6 Call of Pripyat](https://github.com/ixray-team/ixray-1.6-stcop).
Каталог не переносит из этих проектов списки ID: значения читаются из
выбранной установки.

## Локальный read-only probe

| Релиз | Предметы | Именованные предметы | Группировки | Адреса отношений | Локализация | Результат |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Shadow of Chornobyl | 389 | 0 | 0 | 0 | ресурсный образ не найден на хосте | item catalog only |
| Clear Sky | 417 | 271 | 20 | 400 | официальный `xrussian.db` | catalog accepted |
| Call of Pripyat | 434 | 144 | 11 | 121 | официальный `xenglish.db` | catalog accepted |

Для web bundle также проверен официальный resource-source snapshot SoC:
389 предметов, 15 группировок и 225 адресов, limits `-3000…1000`, thresholds
`-400/500`. Он собран из `gamedata/config` репозитория iXRay 1.0 SoC
(commit `a11547a2e4e6426b77ebe4ee19550ab1cab7fdef`) и не является заменой
отсутствующего локального SoC resource image; desktop теперь использует для
этого случая тот же компактный metadata snapshot, что и browser.

В Clear Sky в итоговом каталоге, например, присутствуют resource-derived
`actor`, `csky`, `renegade`, `dolg`, `freedom` и другие ключи; в Call of
Pripyat присутствуют `actor`, `bandit`, `dolg`, `freedom`, `zombied` и другие
ключи. Это наблюдаемый результат установки, а не зашитый список. У каждой
записи сохранены exact key, display name (если есть), numeric ID, release ID
и источник секции; запрос чужого ключа заканчивается `CatalogLookupError`.

## Хэши выбранных ресурсных индексов

Хэши нужны для воспроизводимости локального probe и не содержат игровых
данных в репозитории:

| Ресурс | SHA-256 |
| --- | --- |
| Clear Sky `configs.db` | `90741a73997d73cafbf692c9109811b89725e87c6192d76e6bd373125dec1858` |
| Clear Sky `xrussian.db` | `35adabeea3ecd27c530a33c8ce274660713829c342a61934c838f6307dd8dc6b` |
| Call of Pripyat `configs.db` | `14ec49daee8880106c8fab5b7e38f115319afb4f48a6407b3541fe044d4f0d3a` |
| Call of Pripyat `xenglish.db` | `1d5874c050b128a3464ef86a9eef6112ef14ad829c6c582fab9a4990ae6af981` |

## Front ends и границы

`tools/build_web_catalogs.py` сериализует те же item/faction/relation/upgrade
metadata в `web/catalogs.json`. В браузер не попадают архивы, локальные пути и
сейвы; `web/web_bridge.py` проверяет release ID и не принимает чужие записи.
Если официальный ресурсный корень отсутствует, desktop использует тот же
заранее собранный metadata bundle без прототипов и игровых архивов; локальные
иконки остаются недоступны без официального atlas из установки.

Этот результат подтверждает resource catalog и cross-release isolation. Схема
сериализации faction relations и player community отдельно разобрана в
[XRAY_FACTION_RELATIONS](XRAY_FACTION_RELATIONS_2026-09-15.md), но игровой
load/re-save, Enhanced Edition и совместимость с модами по-прежнему не
подтверждены.
