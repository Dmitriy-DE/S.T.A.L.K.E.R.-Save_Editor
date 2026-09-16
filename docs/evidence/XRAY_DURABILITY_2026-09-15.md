# X-Ray durability — 2026-09-15

Этот файл фиксирует, что удалось подтвердить для прочности предметов в
официальных оригинальных SoC, Clear Sky и Call of Pripyat. Личные сейвы и
игровые архивы в репозиторий не добавлялись.

## Схема из исходников

В публичных исходниках [iXRay 1.0 SoC](https://github.com/ixray-team/ixray-1.0-stsoc),
[iXRay 1.5 Clear Sky](https://github.com/ixray-team/ixray-1.5-stcs) и
[iXRay 1.6 Call of Pripyat](https://github.com/ixray-team/ixray-1.6-stcop)
`CSE_ALifeInventoryItem::STATE_Read/Write` читает и пишет `m_fCondition`
после dynamic-visual state как little-endian `float`. В исходниках это поле
добавлено после старых spawn versions; текущие поддержанные акторы имеют
версии 118 / 124 / 128.

Client-data предмета также содержит сохранённое состояние `CInventoryItem`:
исходник пишет `m_ItemCurrPlace.value` как `u16`, затем condition как `float`.
Перед этими полями у разных оригинальных релизов присутствует различный
physics-prefix, поэтому редактор не фиксирует один абсолютный offset. Он ищет
только тот `float`, который в точности совпадает с подтверждённым STATE
condition, проверяет соседний `u16` по исходному bit layout и принимает место
только при валидном типе и диапазоне slot/base-slot. Так распознаются
`equipped` и `inventory`; неоднозначные и повреждённые значения остаются
`unknown`.

Для weapon/outfit UPDATE-сериализаторы передают условие через `w_float_q8`.
Его исходная формула округляет нормализованное значение в байт `0…255`;
поэтому writer вычисляет mirror как `floor(condition * 255 + 0.5)`. Offset не
зашит по одному совпадению: parser проверяет только относительные позиции 3 и
4 внутри UPDATE и принимает позицию лишь когда `q8 / 255` совпадает с STATE
значением в пределах одного шага квантования. При неоднозначности UPDATE не
трогается, а STATE остаётся отдельным подтверждённым anchor.

## Локальный read-only probe

На одном выбранном официальном файле каждого установленного оригинального
релиза parser получил следующие агрегаты:

| Релиз | Actor-owned weapon/outfit items с condition | Найден q8 mirror | Без безопасного mirror | Диапазон condition |
|---|---:|---:|---:|---:|
| Shadow of Chornobyl | 8 | 7 | 1 | 0.984313…–1.000000 |
| Clear Sky | 6 | 6 | 0 | 0.925490…–1.000000 |
| Call of Pripyat | 7 | 7 | 0 | 1.000000 |

В SoC единственный объект без mirror — сохранённый helmet UPDATE длиной,
недостаточной для безопасного q8 anchor; его STATE condition всё равно
читается, но соседние UPDATE bytes не угадываются.

Точный слот экипировки или ячейка рюкзака в принятом actor registry не
извлекаются надёжно: writer пока не меняет `m_ItemCurrPlace` и не обещает
equip/unequip. UI различает только подтверждённые `equipped`/`inventory`; для
остальных actor-owned предметов показывает `слот не определён`. Это позволяет
редактировать condition обеих групп без догадок о placement.

## Реализация и граница приёмки

- `editor/xray_item_state.py` читает STATE `f32`, находит только совпадающий
  UPDATE `q8` и client-data `f32` mirror с placement, затем патчит все
  подтверждённые mirrors с bounds checks.
- `EditPlan.durability` принимает только уникальные handle и конечные значения
  `0…1`.
- Qt и web показывают состояние в процентах, staged changes не меняют исходные
  bytes до Preview; browser bridge передаёт тот же typed plan.
- Неизвестные families и объекты без подтверждённого anchor остаются
  read-only.

Локально пройдены synthetic tests для трёх версий, parser round-trip на
установленных saves и UI/bridge проверки. Отдельный controlled game
load/re-save именно с изменённой прочностью пока не собран. Поэтому для трёх
оригинальных релизов `FormatCapabilities.edit_durability` включён только как
`experimental_fields`: Qt/web показывают предупреждение, desktop требует
backup, browser не перезаписывает источник. Это разрешает владельцу проверить
подготовленную копию, но не является claim о принятии condition игрой.
