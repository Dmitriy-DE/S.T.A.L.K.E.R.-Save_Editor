# S2 Zone Kit / Steam Workshop catalog evidence — 2026-09-20

## Что добавлено

S2 catalog discovery теперь проверяет следующие loose-источники в таком
порядке:

1. родители выбранного S2 сейва;
2. обнаруженные официальные S2 install roots;
3. явный `STALKER2_ZONE_KIT_ROOT` или `ZONE_KIT_ROOT`;
4. Steam libraries в `steamapps/workshop/content/1643320/<workshop-id>`;
5. явный `STALKER2_WORKSHOP_ROOT`.

Официальные install/Zone Kit roots читаются через canonical
`S2CatalogProvider.load`. Workshop tree читается только через отдельный
`load_overlay` и сохраняет фактический loose content root в `ItemCatalog`.
Overlay не смешивается с официальным каталогом молча и не меняет
`FormatCapabilities`.

Путь должен содержать loose
`Content/GameLite/GameData/ItemPrototypes/*.cfg`. Вложенный Workshop layout
`Stalker2/Mods/<name>/Content/GameLite/GameData` также распознаётся. PAK
архивы, Blueprint assets и бинарные Unreal packages не распаковываются.

## Что подтверждено кодом

- S2 item definitions получают точные prototype SID, display name, category,
  weight, stack, slots и icon path из CFG.
- Standalone upgrade records получают display name, если он реально указан в
  CFG; отсутствующее имя остаётся `None`.
- `ui.xray_assets.XRayIconResolver` читает loose PNG/JPG/WebP/BMP/DDS по
  `ItemDefinition.icon_texture`, включая обычные Unreal object references
  вида `Texture2D'/Game/.../Asset.Asset'`; поэтому Zone Kit/Workshop loose
  icon становится доступен без подмены его случайным предметом.
- Common JSON localization exports under `Content/Localization` and related
  roots resolve `DisplayName` keys to human-readable labels. If no matching
  localization exists, the raw key remains visible instead of an invented
  name.
- `load_overlay` остаётся catalog-only: `add_items`, S2 upgrade writer,
  arbitrary repair и save SID/type-key mapping не включаются.

## Внешнее основание

Официальные материалы GSC описывают Zone Kit как SDK для моддинга и отдельно
показывают работу с item/weapon prototype CFG и Workshop upload:

- [Zone Kit Phase 2](https://www.stalker2.com/news/zone-kit-phase-2-new-features)
- [Zone Kit getting started](https://zonekit-support.stalker2.com/hc/en-us/articles/38198531582481-Getting-started-with-Zone-Kit-or-Zone-Kit-Full-Guide)
- [Zone Kit weapon prototype guide](https://zonekit-support.stalker2.com/hc/en-us/articles/38198715901329-Zone-Kit-Guide-Adding-new-Weapon)
- [S2 Steam Workshop](https://steamcommunity.com/workshop/browse/?appid=1643320&browsesort=mostrecent&section=readytouseitems)

Workshop examples such as
[UpgradeAway - All-in-One](https://steamcommunity.com/sharedfiles/filedetails/?id=3791555216)
and [DurabilityTiers](https://steamcommunity.com/sharedfiles/filedetails/?id=3701257477)
confirm that armor/weapon upgrade and durability behavior is commonly changed
through runtime CFG prototypes (`UpgradePrototypes.cfg`,
`WeaponPrototypes.cfg`, `ArmorPrototypes.cfg`, `NPCPrototypes.cfg`). This is
mod/runtime evidence, not evidence that the same values are serialized into a
portable `.sav` field that this editor may safely rewrite.

## Remaining gate

The repository still does not bundle GSC game assets or private saves. The
tests use private-data-free synthetic trees and now cover localization, direct
icon resolution, explicit catalog-root priority, and nested Workshop roots. A
real S2 catalog count, icon read-back and game load/re-save must be recorded
after the user selects an extracted loose resource root or runs the editor on
a machine with those resources. No Steam cloud write or personal save is part
of this evidence.

The desktop path is intentionally separate from save paths: choose the loose
`Content`/Zone Kit/Workshop root in Settings, then reopen or re-analyse the
save. The selected root supplies names and icons only; it cannot redirect a
local save write or a Cloud upload.
