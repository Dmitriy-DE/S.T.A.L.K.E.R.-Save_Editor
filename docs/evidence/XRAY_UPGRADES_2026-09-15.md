# X-Ray upgrades — 2026-09-15

Этот файл фиксирует границу, которую удалось подтвердить без помещения
личных сейвов в репозиторий. Редактор не использует данные модов.

## Что подтверждено исходниками

В официальных исходниках X-Ray `cse_alife_inventory_item` читает `condition`,
а для версий состояния после `0x7B` — `u32`-счётчик и последовательность
нуле-терминированных строк `m_upgrades`. Этот вектор находится внутри STATE
предмета; при замене меняются только его границы, а последующие поля и UPDATE
пересобираются общим writer-ом.

Каталог не угадывает SID по имени. Он собирается из ресурсов выбранной игры:
`w_*_up.ltx`, outfit upgrade resources и `inventory_upgrades.ltx`, а
applicability привязывается только к exact item-key текущего release.

## Локальный read-only результат

| Релиз | Official item entries | Upgrade definitions | Actor-owned vectors в принятом сейве | Запись |
|---|---:|---:|---:|---|
| Shadow of Chornobyl | 389 | 0 | 0 | read-only: старый STATE без подтверждённого вектора |
| Clear Sky | 417 | 503 | 75 | source-backed in-memory round-trip |
| Call of Pripyat | 434 | 654 | 187 | source-backed in-memory round-trip |

В памяти проверены два length-changing примера: в Clear Sky у
`wpn_vintorez` вектор `4 → 5` с официальным `up_e_vintorez`, в Call of
Pripyat у `exo_outfit` `14 → 15` с официальным `up_firstd_exo_outfit`.
Оба результата повторно разобраны тем же parser-ом; личные файлы не
перезаписывались.

## UI и web

- Qt показывает release-scoped список, сохраняет неизвестные уже записанные
  ID, умеет staged add/remove/clear и не меняет bytes до Preview.
- Browser bridge передаёт тот же `EditPlan`, показывает вектор до/после и
  скачивает новую копию; исходный файл не меняется.
- Для UI-иконок используются координаты `inv_grid_*` из официального каталога.
  Desktop read-only читает официальный `ui_icon_equipment.dds` из unpacked
  `gamedata` или packed resource volume в память. При отсутствии проверенного
  атласа используется repository-owned category glyph; `.dds` и игровые
  шрифты не копируются в Git.

## Что остаётся открытым

- Для S.T.A.L.K.E.R. 2 нет локальной установки/сейва в этом workspace и нет
  подтверждённой именно игровой схемы хранения установленных upgrades. Общие
  GVAS-библиотеки описывают контейнер, но не доказывают STALKER 2 inventory
  semantics; поэтому S2 upgrades остаются read-only.
- Enhanced Edition профили остаются discovery-only до отдельного официального
  образца и game load/re-save.
- Структурный X-Ray round-trip не заменяет отдельную проверку того, что игра
  приняла новый upgrade и сохранила его повторно. Поэтому CS/CoP upgrade
  capability помечена `experimental_fields`, Qt/web предупреждают о backup.
  Запуск игр автоматически не выполнялся.
