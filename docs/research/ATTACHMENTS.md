# X-Ray attachments и upgrades — 2026-09-16

Исследование ограничено официальными оригинальными релизами ТЧ, ЧН и ЗП.
Моды, личные файлы и байты сейвов в репозиторий не попадают. Результат этого
этапа — read-only анализ; mutating writer для attachments пока не открывается.

## Что подтверждено исходником движка

В зафиксированном [OpenXRay xray-16, `CSE_ALifeItemWeapon::STATE_Read`](https://raw.githubusercontent.com/OpenXRay/xray-16/c37860c09850d894b721ba115cd936bb3f11482c/src/xrServerEntities/xrServer_Objects_ALife_Items.cpp)
после базового `CSE_ALifeInventoryItem` состояния идут `a_current` (`u16`),
`a_elapsed` (`u16`) и `wpn_state` (`u8`). Поле `m_addon_flags.flags` читается
ровно одним байтом при `m_wVersion > 40`; затем при более новых версиях идут
`ammo_type` и упакованный счётчик гранат. Это даёт точный anchor только после
разбора всех предшествующих полей, а не по поиску похожего байта.

В [заголовке `CSE_ALifeItemWeapon`](https://raw.githubusercontent.com/OpenXRay/xray-16/c37860c09850d894b721ba115cd936bb3f11482c/src/xrServerEntities/xrServer_Objects_ALife_Items.h)
маски состояния такие:

| Слот | Mask | Значение в `m_addon_flags` |
|---|---:|---|
| scope | `0x01` | при установленном бите scope считается включённым |
| grenade launcher | `0x02` | при установленном бите подствольник считается включённым |
| silencer | `0x04` | при установленном бите глушитель считается включённым |

Остальные биты сохраняются как unknown. Редактор не должен очищать их при
будущей записи.

В [перечислении `EWeaponAddonStatus`](https://raw.githubusercontent.com/OpenXRay/xray-16/c37860c09850d894b721ba115cd936bb3f11482c/src/xrServerEntities/alife_space.h)
статусы конфигурации имеют другую семантику:

| Код | Статус | Правило |
|---:|---|---|
| `0` | disabled | слот отключён |
| `1` | permanent | аксессуар всегда установлен, бит не является переключателем |
| `2` | attachable | аксессуар можно подключать/отключать игровым действием |

`Weapon.cpp` читает `scope_status`, `silencer_status` и
`grenade_launcher_status`. Для attachable scope дополнительно используется
`scopes_sect`; для silencer и grenade launcher движок читает component section
из `silencer_name` и `grenade_launcher_name`. Поэтому effective state нельзя
получать из одного флага: permanent-слоты должны учитываться по конфигу, а
attachable — по state byte.

## Read-only реализация

[`tools/analyze_attachments.py`](../../tools/analyze_attachments.py) теперь:

- разбирает weapon STATE до точного addon-byte anchor с version boundaries;
- показывает `flag_attached_slots`, unknown bits и effective slots после
  применения release-конфига;
- читает официальные weapon LTX из loose `gamedata` либо проверенных
  `resources/*.db` архивов;
- связывает конкретный weapon key с addon statuses, component sections и
  `scopes_sect` options;
- сохраняет уже разобранный `m_upgrades` отдельно, не смешивая upgrades с
  attachments;
- ничего не пишет в сейв и не выводит личный путь в JSON-отчёт.

Пример локального запуска:

```text
python tools/analyze_attachments.py \
  --release stalker-cop \
  --game-root /path/to/Call\ of\ Pripyat \
  /path/to/save.scop
```

Если `gamedata` содержит очевидный community overlay, он пропускается, а
инструмент пытается взять только официальный packed config. На этой машине
так был исключён overlay ЧН; официальные config archives ЧН и ЗП проверялись
отдельно. Для ТЧ подходящего локального config archive нет, поэтому его
compatibility profile остаётся `Unknown`, а не заполняется догадками.

## Локальные наблюдения

Это агрегат read-only probe доступных личных сейвов, не универсальная
характеристика всех сохранений и не game acceptance:

| Релиз | Config profiles | Actor-owned weapons в проверочном сейве | Наблюдаемые флаги |
|---|---:|---:|---|
| ТЧ | 0 | 6 | все `0x00`, profile не найден |
| ЧН | 59 | 4 | все `0x00`; loose mod overlay исключён |
| ЗП | 54 | 6 | пять `0x00`, один `0x04` у `wpn_usp_nimble` |

В расширенном локальном corpus ЗП один и тот же `(handle, weapon key)` в
четырёх случаях встречается со значениями `0x00` и `0x01`. Это полезная
корроборация того, что byte меняется между состояниями, но файлы не являются
контролируемой серией attach/detach: нет зафиксированных трёх состояний,
известного игрового действия и независимого экземпляра с тем же
component/derived-stat diff. Поэтому это не открывает writer.

Отдельно проверено, что у actor-owned weapon records в выбранных сейвах нет
простого набора child objects, который можно было бы безопасно создавать или
удалять вместо state byte. В registry встречаются `wpn_addon_*` объекты с
другими parent edges, но это не доказывает их роль для каждой inventory
операции; orphan/parent совпадение не превращается в reference schema.

## Gate для следующей задачи

Кандидатная операция для будущей R10 должна быть typed и item-scoped:

```text
set_weapon_addons(
    handle,
    scope={enabled, component},
    silencer={enabled, component},
    grenade_launcher={enabled, component},
)
```

Перед записью понадобятся exact weapon profile, attachable status, component
compatibility, занятый slot и все derived/reference updates. Permanent и
disabled нельзя превращать в переключатель, unknown bits нужно сохранить.
Патч только видимого scalar без доказанного companion state запрещён.

Сейчас R09 даёт точный read-only codec и compatibility map, но controlled
attach/detach gate остаётся **BLOCKED**. До game load/re-save/read-back также не
доказано, что изменение конкретного addon в каждом оригинальном build
сохраняется после следующего игрового save. R10 поэтому остаётся закрытой.

Upgrades уже исследованы отдельно: [X-Ray upgrades evidence](../evidence/XRAY_UPGRADES_2026-09-16.md).
Их `m_upgrades` vector нельзя смешивать с addon flags в одной неподтверждённой
операции.
