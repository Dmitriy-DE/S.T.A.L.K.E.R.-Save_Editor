# S.T.A.L.K.E.R. Save Editor

Единый локальный редактор сохранений официальных PC-версий вселенной
S.T.A.L.K.E.R. с подключением Steam Cloud для S.T.A.L.K.E.R. 2.

**Сейчас:** один Qt-редактор и одна статическая web-версия поверх общего
форматного ядра. Зарегистрированы S.T.A.L.K.E.R. 2 и оригинальные Shadow of
Chornobyl, Clear Sky и Call of Pripyat; для оригинальной трилогии принимаются
`.sav` и `.scop` по содержимому контейнера. Desktop умеет auto-discovery
стандартных каталогов, выбор release-specific профиля и ручную папку/файл.

Стартовый экран Desktop — единая Zone-библиотека: он сразу показывает все
четыре семейства игр и найденные локальные сейвы, не выбирая S.T.A.L.K.E.R. 2
по умолчанию. Кнопка `ИМПОРТ СЕЙВА…` принимает скачанный файл без локальной
установки игры, а `STEAM CLOUD` открывает отдельный удалённый поток.

Для всех зарегистрированных форматов доступны локальный анализ, inventory
snapshot, immutable preview и сохранение новой копии. В оригинальной трилогии
доступны деньги, подтверждённые ammo stacks, добавление предметов из
официального каталога и глубокое удаление actor-owned registry records.
Каталог и serializer family берутся из установленной официальной игры на
desktop; в web поставляется компактный metadata-only каталог. Web принимает
локальный файл и ничего не загружает на сервер.

Enhanced Editions уже есть в release selector и path discovery как отдельные
официальные профили, но пока **не зарегистрированы как поддержанные форматы**:
на текущем хосте нет их установок/сейвов и нет достаточного публичного format
evidence. Их нельзя выдавать за совместимые с оригинальным X-Ray parser.
Подробная граница: [EE evidence](docs/evidence/EE_FORMATS_2026-09-15.md).

Плюс остаются browser резервных копий с восстановлением и Desktop-вкладка Steam
Cloud с явным connect/list/analyze/upload. Cloud transport сейчас привязан к
S.T.A.L.K.E.R. 2 (`app_id=1643320`). Если native Steam API подключился, но
вернул пустой список, desktop читает Steam `remotecache.vdf`, а после явного
перезапуска Steam с `-cef-enable-debugging` получает cloud-строки и download URL
из авторизованной web-сессии через localhost CDP. Запись всё равно идёт через
native Steam API. С v0.5.0 облако работает через
**встроенный нативный worker** (`editor/steam_native.py`, ctypes поверх
`libsteam_api`), но с v0.5.6 каждый native-вызов выполняется в отдельном
короткоживущем дочернем процессе с жёстким таймаутом: зависший Steam API больше
не блокирует Qt. Если нативный worker не поднимается, редактор автоматически
откатывается на прежний
`SteamCloudFileManager`, распаковывая его AppImage **без FUSE**
(`--appimage-extract`), что убирает прежний краш `libfuse.so.2`. Библиотека
Valve `libsteam_api` — единственная неустранимая зависимость (её нельзя
заменить чистым Python); она берётся из установленной игры/Steam или из
payload helper'а. Универсальная обратная загрузка Cloud для оригинальной
трилогии и Enhanced Edition не заявляется.
PyInstaller собирает Linux `tar.gz`/`.deb` и Windows `zip`; обе цели проходят
CI вместе с packaged diagnostic на самих раннерах. Декодер: `pyooz==0.0.8` из
wheel, на Linux x86_64 — тот же бинарник из `vendor/ooz.abi3.so`.

Это не означает поддержку модов, Enhanced Edition или любого неизвестного
патча: проект принимает только официальные зарегистрированные profiles и
отказывает закрыто, если контейнер/версия/границы не подтверждены.

## Что доступно

- S.T.A.L.K.E.R. 2: чтение и изменение денег/подтверждённых стаков с
  сохранением CRC/Kraken safeguards. Структура GVAS-инвентаря и добавление
  предметов пока не включены без доказанной схемы.
- Original Shadow of Chornobyl, Clear Sky и Call of Pripyat: strict X-Ray
  container, actor money, полный actor-owned inventory snapshot, официальные
  catalog keys и serializer families. Ammo count пишется одновременно в
  STATE и UPDATE.
- Для оригинальной трилогии writer умеет добавить предмет из каталога,
  клонировав существующий registry template той же подтверждённой
  serializer family, и удалить actor-owned record с новым registry framing.
  Если в конкретном сейве нет подходящего template или нет каталога, операция
  отказывается; game load/re-save этого результата ещё не подтверждён.
- CRC32, распаковка Kraken, пересборка и побайтовая проверка round-trip.
- Qt-интерфейс для локальных файлов и Steam Cloud; веб-версия для локальных
  файлов; CLI для исследования. Все три используют одно ядро.
- CLI поддерживает batch-редактирование денег/стаков и добавление из официального каталога
  (`edit --add ITEM=COUNT`); experimental остаются move, detach/deep detach,
  attach существующего orphan, raw patch и diff-record.
- Общий UI-free `EditorService` связывает parser, immutable preview, local export,
  backup restore и cloud transaction; интерфейс и CLI ходят через него, своей
  логики правок не имеют.
- Cloud tab не вызывает helper при старте: сначала явное подключение и список
  `Data/*.sav`; при пустом API показывает Steam cache и предлагает одной
  кнопкой перезапустить Steam с CEF debug, затем анализирует выбранный slot и
  upload-ит только его preview.
- Интерфейс следует визуальному референсу Zone: demo-данные макета не
  копируются, badges, cards и таблица метаданных заполняются только из
  реального snapshot.

**Не реализовано как подтверждённые production-функции:** полноценная
inventory grid/move/equipment-семантика, изменение прочности,
attachments/upgrades, reference-safe удаление квестовых/equipped объектов,
локализованные названия для всех ключей и структурное добавление в S.T.A.L.K.E.R.
2. Unknown fields остаются read-only; X-Ray structural proof не означает, что
игра уже проверила результат загрузкой.

Cloud-процесс использует fresh SHA, exclusive backup/recovery, persisted и
read-back; после WriteFile state machine различает `verified` и `uncertain` и
не повторяет upload автоматически. Worker lifecycle покрыт fake helper, но
работа с реальным Steam/GFN в этом репозитории ещё не проверена. Локальный
export использует общий backup/atomic path после S03. Остальные ограничения:
[состояние и пробелы](docs/STATUS.md).

## Запуск из исходников

Нужен Python 3.11+. Проверялся x86_64 Linux, не все дистрибутивы.

```bash
python3 -m pip install -r requirements.txt
python3 -m ui
```

На Windows: `py -3 -m pip install -r requirements.txt` и `py -3 -m ui`.

В интерфейсе можно искать и фильтровать локальный inventory, застейджить
подтверждённые money/stack изменения, добавить предмет из каталога или удалить
actor-owned record, нажать preview и сохранить новую копию.
На вкладке резервных копий видны hash/status журнала; проверенный backup можно
восстановить в новый путь, а исходный сейв и backup остаются неизменными. На
вкладке Steam Cloud upload показывает `verified` или `uncertain`; после
`WriteFile` автоматического повтора нет.

Steam (запущенный клиент) нужен только для cloud-режима. Нативные вызовы
выполняются в короткоживущем дочернем процессе с жёстким таймаутом, поэтому
зависший `SteamAPI_Init`/RemoteStorage не блокирует Qt; при сбое первичного
списка доступный helper остаётся ограниченным fallback. Source и локальный
standalone smoke подтверждают `init + connect + list` с пустым списком на этом
хосте; реальный `download → edit → upload` пользовательский сейв не проверен.
Cloud-upload из автоматических тестов блокируется в коде: и `SteamWorker`, и
`SteamNativeWorker` отказывают в `Connect`/`WriteFile` для app_id игры под
pytest, пока не выставлен `STALKER2_ALLOW_LIVE_CLOUD=1` для осознанного
ручного прогона.

## Веб-версия

Тот же редактор работает в браузере: `web/` — статическая страница, которая
запускает **то же самое Python-ядро** через Pyodide и получает единственный
нативный вызов (распаковка Kraken) из `ooz-wasm`. Второго парсера нет:
`web/pysrc.json` генерируется из исходников репозитория, а `make docs-check`
падает, если он отстал.

```bash
make web-serve      # http://localhost:8765
```

Файл никуда не загружается: читается в этой же вкладке и обрабатывается в
WebAssembly. Сервера у приложения нет.

Онлайн-версия работает здесь:
**<https://stalker-save-editor.pages.dev>**

Обновляется одной командой `make web-deploy` (Cloudflare Pages). Сервера у приложения нет — отдаётся только статика, а
редактор целиком исполняется в браузере посетителя.

Что доступно в вебе: открыть локальный `.sav`, `.scop` или другой файл для
content-only detection, увидеть определённый release/edition, деньги,
инвентарь и технические метаданные, поменять подтверждённые money/ammo stacks,
добавить предмет из встроенного официального metadata-каталога, удалить
actor-owned record и скачать изменённую копию. Capability flags и read-only
причины приходят из того же registry, что и в desktop. Проверка S2 и
оригинального X-Ray bridge зафиксирована в
[evidence](docs/evidence/WEB_EDITION_2026-09-14.md) и
`docs/evidence/XRAY_INVENTORY_2026-09-15.md`.

Чего в вебе нет: **Steam Cloud** (helper — локальный процесс рядом со Steam,
вкладка браузера его не запустит) и журнала резервных копий (в браузере нет
каталога бэкапов, поэтому страница прямо требует сохранить оригинал самому).
Разобранные альтернативы для облака: [STEAM_CLOUD_OPTIONS](docs/evidence/STEAM_CLOUD_OPTIONS.md).

## Standalone-пакеты

В исходном режиме Python нужен только для запуска проекта. Для пользователя
готового bundle Python и `pip` не нужны: PyInstaller вкладывает интерпретатор,
PySide6/Qt plugins и native decoder. Core parser/storage остаются на
стандартной библиотеке; SteamCloudFileManager не вкладывается и выбирается как
отдельный helper.

Сборка выполняется на целевой ОС, потому что PyInstaller не cross-компилирует:

```bash
# Linux x86_64 (окружение с requirements-build.txt и dpkg-deb)
python packaging/build.py --target linux --output-dir dist

# Windows x64 (Windows Python 3.11 build environment)
py -3 packaging/build.py --target windows --output-dir dist
```

Linux создаёт `SaveEditor-linux-x86_64-v*.tar.gz` и
`stalker2-save-editor_*_amd64.deb`; Windows —
`SaveEditor-windows-x86_64-v*.zip`. Каждый запуск создаёт `SHA256SUMS`, а
внутри bundle лежат `BUILD_MANIFEST.json`, `SOURCE_COMMIT.txt`, notices и
provenance native decoder. `SaveEditor-diagnostic --diagnostic` проверяет
вложенный Qt/decoder без открытия окна. `dist/` не коммитится и автоматический
GitHub Release до B02 не выполняется.

Новые настройки и backups пишутся в platform user-data directory
(`$XDG_DATA_HOME/Stalker2SaveEditor` или `~/.local/share/Stalker2SaveEditor` на
Linux, `%APPDATA%\Stalker2SaveEditor` на Windows). Старый
`~/Stalker2SaveEditor` читается как legacy fallback и не перемещается/удаляется.

```bash
python3 cli.py info /path/to/save.sav
make check
make selftest SAVE=/path/to/original-save.sav
```

Текущая пересборка увеличивает файл примерно с 6–7 до 27 MB. Round-trip подтверждает байты, но не игровую семантику. Проверять experimental-результат нужно загрузкой и повторным сохранением в игре на копии слота.

## Разработка и задачи

1. [Текущее состояние и найденные ограничения](docs/STATUS.md).
2. [Спецификация Linux/Windows и UI](docs/specs/CROSS_PLATFORM_EDITOR.md).
3. [План этапов и зависимостей](docs/plans/ROADMAP.md).
4. [Пошаговые задачи](docs/tasks/INDEX.md).
5. [Инструкция для GPT-5.6 Luna](docs/LUNA_HANDOFF.md).
6. [Проверка и выпуск](docs/RELEASE.md).
7. [Навигация по документации](docs/README.md).

## Локальные материалы

Исторические архивы v0.1/v0.3 удалены из дерева: они остаются в истории Git, а
бинарные сборки публикуются в GitHub Releases после проверки на обеих ОС.

Исходные материалы владельца сохранены в `.local/original-import-2026-09-13/`, исключены из Git. Там находятся личные `.sav`, скриншоты, полный handoff, исходные архивы и manifest. При клонировании GitHub эти файлы не появятся; приложение и будущие синтетические тесты не должны от них зависеть.

## Лицензия

GPL-3.0, см. [LICENSE](LICENSE) и [зависимости](THIRD_PARTY_NOTICES.md). Игра, игровые ассеты и SteamCloudFileManager в дистрибутив приложения не включены. Проект не является официальным инструментом GSC или Valve.
