# S.T.A.L.K.E.R. 2 equipment condition writer — 2026-09-19

Этот документ фиксирует границу экспериментальной поддержки состояния
экипировки. Личные сейвы, распакованные payload bytes и содержимое Steam Cloud
в репозиторий не добавляются. Для расположения локальных копий используется
уже принятый [S2 save-location evidence](SAVE_LOCATIONS.md).

## Что подтверждено

В одном actor-owned S2 object с `kind=1` одновременно выполняются все
условия безопасного anchor:

1. handle находится в верхней записи объекта;
2. тот же little-endian handle повторяется по адресу `record_offset + 0x23`;
3. по адресу `record_offset + 0x27` лежит little-endian `f32` в диапазоне
   `0…1`;
4. object входит в actor-owned handles и не является unresolved orphan.

В локальном differential corpus четыре независимых `kind=1` записи проходили
эту nested-shape проверку; в наблюдавшихся парах значение было `0.75`. В
отдельном actor-owned экипированном объекте Exoskeleton parser прочитал
`0.9745476246`, показал запись как `экипировано` и разрешил staged изменение.
Эти наблюдения подтверждают форму поля, но не утверждают, что каждая броня,
оружие или версия игры использует тот же layout.

Свежий read-only scan настроенного локального S2 `SaveGames/Data` root увидел
51 `.sav`: 33 файла разобрались текущим inventory parser-ом, 18 были честно
отклонены до inventory из-за отсутствующего уникального wallet anchor. В
разобранных файлах получено 1 153 inventory rows, включая 297 equipped rows и
33 `kind=1` armor rows; все 33 armor rows прошли exact anchor guard. До и после
сканирования SHA-256 и `mtime_ns` каждого файла совпали; scan ничего не писал.

Классификация не выводится из одного `kind=1`: embedded save-local name table
используется для exact suffix `_Armor`/`_Helmet`. Поэтому `GunBucket_*`, grid
rows и modifier names вроде `*_Armor_PSY_*` не получают armor writer только из-за
похожего kind или имени. Loose official CFG catalog дополнительно даёт
display-name/icon metadata, когда установленная игра предоставляет такие
ресурсы; при packed-only install UI показывает честный category glyph.

Реализация в `editor/s2_item_state.py` пишет только четыре байта этого
подтверждённого `f32`. Перед записью она проверяет kind, оба handle и диапазон;
после container rebuild `save_format.patch_save` повторно читает каждое
запрошенное значение и отклоняет transaction при расхождении. Preview не
меняет исходные bytes, а capability помечена как experimental.

## Что намеренно остаётся read-only

| Возможность | Граница | Что нужно до включения |
|---|---|---|
| Condition оружия | В текущем corpus нет принятого differential anchor для weapon writer | Контролируемая пара «один weapon повреждён/починен» с однозначным handle, полем и game read-back |
| Upgrades экипировки | Наблюдаемые upgrade-key arrays не разделены надёжно на installed/current и available/applicable | Пара с ровно одной установленной игрой upgrade и подтверждённым сериализатором всех affected references |
| Выдать предмет из каталога | Official CFG/SID описывает prototype metadata, но не является доказанным constructor для `.sav` object registry | Пара с ровно одним pickup, allocator/handle, owner/grid/stack/reference edges и game read-back |

Поэтому S2 capability открывает только экспериментальную condition-правку
подтверждённой брони. `add_items`, S2 upgrades и неподтверждённая weapon
condition остаются выключенными; неизвестные records не превращаются в
предметы только из-за похожего имени или соседнего `f32`.

## Controlled-pair protocol

Все шаги выполняются пользователем вручную на копиях вне живого Cloud slot.
До любого эксперимента сохранить исходный файл и SHA-256. Codex не запускает
игру и не пишет в игровую папку.

### 1. Одна известная броня

1. В игре сделать отдельный ручной save `armor-before`: экипировать одну
   конкретную броню и записать её название/состояние.
2. Выполнить ровно одно действие, меняющее condition (например, получить
   повреждение), и сохранить `armor-after` в новый slot. Не менять оружие,
   инвентарь, задания или upgrades между двумя saves.
3. В редакторе сравнить распакованные копии: должен сохраниться тот же
   actor-owned handle, type/name и object-reference graph; должен измениться
   только подтверждённый condition anchor и необходимые CRC/Kraken metadata.
   Любой дополнительный diff сначала классифицируется, а не игнорируется.
4. Открыть `armor-before` в редакторе, застейджить новое значение condition,
   сделать Preview/Save в новую локальную копию и проверить fresh SHA,
   decompression/CRC round-trip и post-rebuild read-back.
5. Загрузить эту копию в игру, убедиться, что игра принимает save, затем
   снова сохранить его. Новый game save должен сохранить тот же object handle,
   показать ожидаемую прочность и снова пройти parser read-back.

Только после этой строки evidence можно считать armor condition game-accepted;
до неё статус остаётся experimental.

### 2. Один известный upgrade

Сделать `upgrade-before` и `upgrade-after` с одной и той же бронёй, установив
ровно один известный upgrade и не меняя другие поля. В diff нужно доказать:

- однозначную запись установленного upgrade и её границы;
- какие arrays являются installed/current, а какие available/applicable;
- связь upgrade с owner/object handle и отсутствие скрытого удаления/добавления;
- валидный container round-trip и game load/re-save после записи редактором.

Пока эти условия не выполнены, writer не трогает ни одну из двух наблюдаемых
upgrade-key arrays.

### 3. Один pickup из каталога

Сделать `item-before` и `item-after`, подняв в игре ровно один известный
предмет из официального каталога. Зафиксировать type/prototype key, количество
и место в инвентаре. В diff нужно найти и подтвердить одновременно:

- allocator нового handle и полную object record;
- prototype/type binding, owner reference и grid/stack placement;
- все обязательные dependent references, которые игра создаёт вместе с item;
- отсутствие случайного клонирования существующего объекта;
- game load/re-save для файла, созданного writer-ом.

Одного SID из metadata-каталога недостаточно: до такой пары `add_items` остаётся
запрещённым.

### 4. Cloud только после локального acceptance

Сначала пройти локальный load/re-save и сохранить backup/read-back SHA. Только
после этого выбрать отдельный Cloud slot, скачать его через текущий Cloud flow,
применить ту же transaction и проверить persisted/read-back SHA. Live upload
не заменяет игровую проверку и не должен быть первым местом эксперимента.

## Current verdict

Экспериментальная правка condition подтверждённой S2 брони реализована с
точным anchor, backup/preview и post-rebuild guard. Игра ещё не выполнила
controlled load/re-save для этой правки в рамках этого evidence, поэтому
заявлять полную поддержку экипировки, upgrades, выдачи предметов или weapon
condition нельзя.
