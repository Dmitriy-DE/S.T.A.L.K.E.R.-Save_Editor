# X-Ray inventory placement — 2026-09-16

Этот файл фиксирует только подтверждённую границу переноса предметов между
слотами, поясом и рюкзаком в официальных оригинальных SoC, CS и CoP. Enhanced
Editions, S.T.A.L.K.E.R. 2, моды и личные сейвы не входят в scope. Read-only
проба не записывает найденные файлы; загрузка изменённого сейва игрой и
повторное сохранение по M10 не выполнялись.

## Сериализация из исходников

В OpenXRay [inventory_item_object.cpp, pinned commit
`c37860c`](https://github.com/OpenXRay/xray-16/blob/c37860c09850d894b721ba115cd936bb3f11482c/src/xrGame/inventory_item_object.cpp#L102-L106)
обычный inventory object сначала сохраняет унаследованное физическое
состояние, а затем `CInventoryItem::save`. Унаследованный
[PhysicsShellHolder.cpp](https://github.com/OpenXRay/xray-16/blob/c37860c09850d894b721ba115cd936bb3f11482c/src/xrGame/PhysicsShellHolder.cpp#L350-L359)
записывает один `u8 enable_state`; следующий
[inventory_item.cpp](https://github.com/OpenXRay/xray-16/blob/c37860c09850d894b721ba115cd936bb3f11482c/src/xrGame/inventory_item.cpp#L359-L363)
записывает `m_ItemCurrPlace.value` как little-endian `u16`, затем condition.
Поэтому подтверждённая граница `SInvItemPlace` в client-data у трёх
поддержанных релизов — `client_data_offset + 1`.

`SInvItemPlace` — это source-defined bitfield: нижние 4 бита содержат тип,
следующие 6 — `slot_id`, ещё 6 — `base_slot_id`. Типы `Slot`, `Belt` и `Ruck`,
а также диапазон слотов 1…13 сверены с
[inventory_space.h](https://github.com/OpenXRay/xray-16/blob/c37860c09850d894b721ba115cd936bb3f11482c/src/xrServerEntities/inventory_space.h)
и с чтением/записью item place в
[inventory_item.cpp](https://github.com/OpenXRay/xray-16/blob/c37860c09850d894b721ba115cd936bb3f11482c/src/xrGame/inventory_item.cpp#L752-L760).
Игровые операции слота, пояса и рюкзака также видны в
[Inventory.cpp](https://github.com/OpenXRay/xray-16/blob/c37860c09850d894b721ba115cd936bb3f11482c/src/xrGame/Inventory.cpp#L414-L417).

## Граница редактора

Codec читает ровно два байта по release-specific offset и не сканирует
соседние данные в поисках подходящего значения. Изменение разрешается только
для actor-owned inventory object с подтверждённым client-data anchor:

- `slot` принимает номер 1…13 и меняет type/slot, сохраняя `base_slot_id` и
  прочие верхние биты;
- `belt` и `ruck` принимают `None` вместо номера слота и меняют только type,
  сохраняя остальные биты;
- отсутствующий, неизвестный или неподтверждённый place остаётся read-only;
- writer меняет только этот `u16`, после чего выполняются обычные CRC,
  decompression/rebuild, fresh SHA и повторный parse/read-back guards.

Qt и web используют один immutable `EditPlan.placements`, показывают before →
after и сначала только staging/preview. Для original SoC/CS/CoP capability
помечена experimental; для S2 и Enhanced она не включается.

## Read-only корпус

Проверены копии официальных оригинальных релизов локально, без записи в
исходные файлы. Числа ниже — агрегаты конкретного корпуса, а не утверждение
о каждом возможном сейве:

| Релиз | Файлы parsed/failed | Inventory objects | Editable place | Типы | Storage |
| --- | ---: | ---: | --- | --- | --- |
| Shadow of Chernobyl | 6 / 0 | 373 | 328 | belt 25, ruck 303 | inventory 328 |
| Clear Sky | 59 / 0 | 4486 | 4034 | belt 114, ruck 3920 | inventory 4034 |
| Call of Pripyat | 171 / 0 | 27373 | 27373 | belt 616, ruck 25276, slot 1481 | equipped 1481, inventory 25892 |

Проба подтвердила, что offset `1` даёт согласованное распределение и
отсутствие parse failures на этом корпусе. Это структурное и read-only
evidence; оно не доказывает, что каждая конкретная версия игры примет новый
place или корректно покажет его после следующего игрового сохранения.

## Проверки

- `tests/test_xray_placement.py`: release-specific offsets, slot/belt/ruck,
  сохранение metadata и отказ unsafe anchors;
- `tests/test_ui_placement.py`: Qt staging и неизменность snapshot;
- `tests/test_web_bridge.py`, `tests/test_web_inventory_icons.py`:
  cross-platform bridge и web controls;
- `make check`, `make test`, `node --check web/app.js`, `git diff --check`.
