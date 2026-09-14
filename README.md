# S.T.A.L.K.E.R. 2 HoC — Save Editor

Локальный редактор сохранений с подключением Steam Cloud для игры через GeForce NOW.

**Сейчас:** один Qt-редактор в Zone-теме поверх общего ядра: локальный анализ,
поиск и фильтры по инвентарю, staged money/stack edits, immutable preview и
сохранение в новую копию, browser резервных копий с восстановлением и вкладка
Steam Cloud с явным connect/list/analyze/upload. Плюс CLI для исследования.
PyInstaller собирает Linux `tar.gz`/`.deb` и Windows `zip`; Linux bundle
подтверждён локально, Windows runner smoke ещё впереди. Декодер: `pyooz==0.0.8`
из wheel, на Linux x86_64 — тот же бинарник из `vendor/ooz.abi3.so`. Это
исследовательская версия, не готовый универсальный редактор.

## Что доступно

- Чтение и изменение денег; изменение количества распознанных стаков с пересчётом веса.
- CRC32, распаковка Kraken, пересборка и побайтовая проверка round-trip.
- Qt-интерфейс для локальных файлов и Steam Cloud; CLI для исследования.
- Experimental в CLI: move, detach/deep detach, attach существующего orphan, raw patch и diff-record.
- Общий UI-free `EditorService` связывает parser, immutable preview, local export,
  backup restore и cloud transaction; интерфейс и CLI ходят через него, своей
  логики правок не имеют.
- Cloud tab не вызывает helper при старте: сначала явное подключение и список
  `Data/*.sav`, затем анализ выбранного slot и upload только его preview.
- Интерфейс следует визуальному референсу Zone: demo-данные макета не
  копируются, badges, cards и таблица метаданных заполняются только из
  реального snapshot.

**Не реализовано как подтверждённые функции:** создание предмета по SID, клонирование, физическое удаление, прочность, attachments/upgrades, полные названия предметов. `detach` не означает физическое удаление.

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
подтверждённые money/stack изменения, нажать preview и сохранить новую копию.
На вкладке резервных копий видны hash/status журнала; проверенный backup можно
восстановить в новый путь, а исходный сейв и backup остаются неизменными. На
вкладке Steam Cloud upload показывает `verified` или `uncertain`; после
`WriteFile` автоматического повтора нет.

Steam нужен только для cloud-режима, helper устанавливается отдельно.
Cloud-upload из автоматических тестов блокируется в коде: `SteamWorker`
отказывает в `Connect`/`WriteFile` для app_id игры под pytest, пока не
выставлен `STALKER2_ALLOW_LIVE_CLOUD=1` для осознанного ручного прогона.

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
