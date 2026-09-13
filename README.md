# STALKER 2 Cloud Save Editor — Linux — v0.3.0 EXPERIMENTAL

Проект для сценария **Steam Cloud → скачать save → backup → отредактировать → проверить контейнер/структуру → загрузить обратно в тот же Steam Cloud slot** без установки самой игры.

> **Статус:** money и stack-count подтверждены на реальных сейвах. Move / detach / attach-orphan / raw patch включены специально для тестирования и reverse engineering; они проходят структурный round-trip, но поведение внутри игры ещё нужно подтверждать вручную. Всегда держи backup.

## Быстрый старт

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install -y python3 python3-tk
```

Скачай Linux x64 SteamCloudFileManager:

- https://github.com/Fldicoahkiin/SteamCloudFileManager/releases

Steam должен быть запущен и авторизован.

Запуск:

```bash
cd stalker2-cloud-save-editor-v0.3.0-experimental
./run.sh
```

В GUI:

1. Укажи `SteamCloudFileManager*.AppImage`/binary.
2. Нажми **Подключить / обновить**.
3. Выбери `Stalker2/Saved/STEAM/SaveGames/Data/*.sav`.
4. Нажми **Анализировать cloud-save**.
5. Сделай правки.
6. Нажми **BACKUP → APPLY → VERIFY → UPLOAD/EXPORT**.
7. Не запускай GeForce NOW, пока не увидишь `persisted=true` и успешный read-back SHA.

Можно также открыть локальный `.sav` кнопкой **Открыть локальный .sav…** и сохранить edited-copy без Steam.

---

## Что работает

### Подтверждено / safe-ish

- проверка CRC32;
- распаковка Oodle/Kraken через bundled `ooz.abi3.so`;
- чтение текущих купонов;
- изменение купонов;
- разбор реального player inventory grid;
- чтение object handle, x/y, footprint, count, cached stack weight, category-kind;
- изменение количества существующих stackable items (`count > 1`);
- пересчёт cached total stack weight;
- несколько правок за один проход;
- backup исходника;
- full decompression round-trip после пересборки;
- stale-cloud SHA256 guard;
- upload в **тот же** Steam RemoteStorage path;
- ожидание `is_persisted=true`;
- read-back из облака и повторная SHA/CRC/Kraken проверка.

### Включено для тестирования — EXPERIMENTAL

- **Move item**: меняет x/y object record и все grid-cell coordinates этого object handle;
- **Detach**: удаляет grid-cells выбранного объекта и ставит record x/y = `0xFFFF`;
- **Deep detach**: дополнительно удаляет object handle из owned-handle array;
- **Attach orphan**: берёт уже существующий owned handle, которого нет в grid, и добавляет ему footprint в выбранную позицию;
- **Raw record patch**: запись `u8/u16/u32/i32/f32/hex` в raw decompressed payload;
- **Object record hex viewer**;
- CLI `diff-record` для сравнения одного object handle между двумя сейвами.

Это даёт реальную тестовую площадку для поиска durability, SID/prototype reference, attachments и других полей без необходимости каждый раз писать отдельный скрипт.

---

## Чего пока НЕТ как подтверждённой функции

- настоящий `Add item by SID` с созданием **нового** object record и нового handle;
- настоящий clone оружия/брони как отдельного object instance;
- гарантированное physical delete object record из глобального object graph;
- подтверждённое поле durability;
- автоматическое отображение всех внутренних объектов по Game8/GamerGuides названию;
- изменение attachments/upgrade state.

Почему: для этого мало изменить одну цифру. Нужно подтвердить сериализацию object registry / prototype reference / handle allocation / dependent references. `v0.3` специально включает raw/diff/structural lab, чтобы это можно было быстро добить и тестировать.

---

# GUI

## Купоны

Вкладка **Купоны**:

```text
[✓] Изменить баланс при применении
Новая сумма: 900000
```

Поле money было найдено сравнением реальных сейвов с известными UI-значениями: `48645`, `58870`, `56995`.

## Инвентарь

Таблица показывает:

```text
x,y | size | category | type-key | count | weight | object handle
```

`type-key` — исследовательский 3-byte ключ из object record (`+8..+10`). Он стабилен между соседними сейвами для того же объекта, но **пока не объявлен SID/hash**.

Stack editor разрешает только подтверждённые записи `count > 1`, не weapon/armor.

## Экспериментально

Сначала включи checkbox риска.

### Move

Выбери предмет → введи `x`, `y` → **Stage move**.

Редактор:

- проверяет границы 8-column grid;
- учитывает footprint;
- блокирует collision с другим handle;
- патчит object-record position и все grid cells.

### Detach

**Stage DETACH** удаляет grid references объекта и выставляет record position `FFFF,FFFF`.

`Deep detach` дополнительно удаляет handle из owned-handle list.

Это **не доказанный delete объекта из object graph**. Название в коде намеренно `detach`, а не `delete_object`.

### Attach orphan

В левой таблице показаны owned handles, которые не представлены в grid. Среди них могут быть equipped/hidden/system objects, поэтому это опасная функция.

Укажи `x,y,w,h` → **Stage ATTACH orphan**.

### Raw record lab

Выбери inventory item. Справа появится hex window его object record.

```text
offset: +0x20
kind: f32
value: 1.0
```

- `+0xNN` — offset относительно selected object record;
- `0xNN` — абсолютный raw payload offset.

Поддерживаются:

```text
u8 u16 u32 i32 f32 hex
```

Это основной инструмент для поиска durability и неизвестных полей через контролируемые diff-сейвы.

---

# CLI

## Информация

```bash
python3 cli.py info save.sav
```

## Инвентарь

```bash
python3 cli.py inventory save.sav --all
python3 cli.py orphans save.sav
```

## Деньги

```bash
python3 cli.py set-money save.sav 900000
```

## Stack

```bash
python3 cli.py set-stack save.sav 0x300027c8 99
```

## Move — experimental

```bash
python3 cli.py move save.sav 0x30000e1e 0 20
```

## Detach — experimental

```bash
python3 cli.py detach save.sav 0x30000e1e
python3 cli.py detach save.sav 0x30000e1e --deep
```

## Attach existing orphan — experimental

```bash
python3 cli.py orphans save.sav
python3 cli.py attach-orphan save.sav 0x30002662 0 20 1 1
```

## Raw patch — experimental

```bash
python3 cli.py raw save.sav 0x123456 f32 1.0
```

## Object record dump

```bash
python3 cli.py dump-record save.sav 0x30000e86 --limit 1024
```

## Diff одного object handle между двумя сейвами

```bash
python3 cli.py diff-record before.sav after.sav 0x30000e86 --limit 2048
```

Это наиболее полезная команда для поиска durability: сделай два сейва, где изменилось только состояние нужного оружия, и сравни один и тот же handle.

## Batch

```bash
python3 cli.py edit save.sav \
  --money 900000 \
  --stack 0x300027c8=99 \
  --move 0x30000e1e=0,20 \
  --detach 0x3000874a \
  --raw 0x123456:f32:1.0
```

---

# Подтверждённый save container

```text
u32 LE unpacked_size
Oodle/Kraken stream
u32 LE CRC32(all preceding bytes)
```

Распаковка:

```python
raw = ooz.decompress(file[4:-4], unpacked_size)
```

Сейчас editor пересобирает raw в валидные uncompressed Kraken restart blocks по `0x40000` с header `CC 06`. Поэтому edited save получается около 27 MB вместо исходных ~6–7 MB. Это намеренно: не нужен proprietary Oodle compressor, а round-trip детерминированный.

---

# Подтверждённый player inventory layout

Уникальный `MONEY_ANCHOR` → `u32 money`, затем:

```text
u32 owned_flag             # observed = 1
u16 owned_handle_count
u32 owned_handles[count]
u16 grid_cell_count
GridCell cells[count]
```

`GridCell`:

```c
struct GridCell {
    uint32 object_handle;
    uint16 x;
    uint16 y;
};
```

Grid width = 8.

Повтор одного handle в нескольких cells = footprint предмета.

На реальном save `D639...`:

- `owned_handle_count = 53`;
- `grid_cell_count = 65`;
- parser сопоставляет 34 visible inventory objects;
- есть 14 owned handles без grid cells.

---

# Подтверждённая часть object record

Для object record, начинающегося с `u32 handle`:

```text
+0   u32 handle
+8..+10  research type-key (3 bytes, semantics not confirmed)
+11  u16 inventory x
+13  u16 inventory y
+18  byte 0x38 marker
+19  u32 stack count
+24  f32 total/cached stack weight
+31  u8 category-kind
```

`count` и `weight` подтверждены по множеству UI stacks: `34`, `10`, `21`, `3`, `2`, `6`, `20`, `211`, `60`, `60`, `62`, `25` и др.

Позиция `+11/+13` подтверждена сравнением object records и grid coordinates.

---

# Research / похожие решения

Изучались:

- **SteamCloudFileManager** — Steamworks RemoteStorage backend; проект использует его отдельным helper через `--steam-worker`:  
  https://github.com/Fldicoahkiin/SteamCloudFileManager
- **Fire Save Repair** — пример fail-closed offline patcher для STALKER 2:  
  https://www.nexusmods.com/stalker2heartofchornobyl/mods/2601
- **Stalker2Control** — каталог item spawning / console commands:  
  https://github.com/Rianvy/Stalker2Control
- **Console item command list**:  
  https://github.com/scalespeeder/stalker-2-pc-console-common-useful-commands-list
- **GamerGuides item DB** — полезна для human name ↔ SID каталога:  
  https://www.gamerguides.com/stalker-2-heart-of-chornobyl/database/
- **Game8 wiki** — human-facing item/wiki данные:  
  https://game8.co/games/STALKER-2-Heart-of-Chornobyl
- **GSC Zone Kit Phase 2** — официально подтверждает расширенную Save/Load modding поддержку, что может помочь дальнейшему reverse engineering:  
  https://www.stalker2.com/news/zone-kit-phase-2-new-features
- **Zone Kit docs**:  
  https://zonekit-support.stalker2.com/

`data/item_ids_seed.json` содержит маленький seed публичных console SIDs. Это пока reference, не offline save mapping.

---

# Тесты

Проверка синтаксиса:

```bash
make check
```

Self-test на реальном сейве:

```bash
make selftest SAVE=/path/to/D639C0F24C64FC164326E8967A8DCCBE.sav
```

Self-test проверяет:

- CRC/decompress/parser;
- stack edit;
- move structural round-trip;
- detach structural round-trip;
- attach-orphan structural round-trip;
- raw-patch pipeline.

Важно: self-test доказывает **целостность контейнера и нашей распознанной структуры**, а не то, что игра семантически принимает экспериментальный detach/attach. Это проверяется только загрузкой в STALKER 2 / GeForce NOW.

---

# Steam Cloud safety

Перед upload приложение:

1. заново скачивает выбранный cloud save;
2. сравнивает SHA256 с анализированным;
3. сохраняет `*_ORIGINAL.sav`;
4. патчит;
5. пересобирает и повторно распаковывает;
6. проверяет known structures;
7. сохраняет `*_EDITED.sav` recovery copy;
8. делает `WriteFile` в тот же path;
9. вызывает sync;
10. ждёт `is_persisted=true`;
11. скачивает файл обратно и сверяет SHA/CRC/decompression.

Backups:

```text
~/Stalker2SaveEditor/backups/
```

Не запускай GFN до успешного read-back.

---

# Для Codex / следующего разработчика

Сначала прочитать:

1. `README.md`
2. `docs/SAVE_FORMAT.md`
3. `docs/CODEX_HANDOFF.md`
4. `docs/EXPERIMENTAL.md`
5. `NOTES_FROM_RESEARCH.md`

Главные следующие задачи:

1. подтвердить prototype/SID reference в object record;
2. построить `SID → save representation` по Zone Kit/config dumps;
3. определить полноценные boundaries/object registry array;
4. реализовать allocate-new-handle + clone/new object instance;
5. Add item by SID;
6. real delete с cleanup dependent refs;
7. durability через controlled diff;
8. attachments/upgrades;
9. compact mixed-block rebuild вместо 27 MB output;
10. автоматический item catalog updater.

**Не переписывай safe paths ради красивого UI.** Money/stack/cloud guards уже проверены; experimental слой должен оставаться отдельно и fail-closed.

---

# License

GPL-3.0. См. `LICENSE` и `THIRD_PARTY_NOTICES.md`.
