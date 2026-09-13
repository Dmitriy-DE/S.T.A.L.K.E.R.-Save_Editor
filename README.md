# S.T.A.L.K.E.R. 2 HoC — Save Editor

Локальный редактор сохранений с подключением Steam Cloud для игры через GeForce NOW.

**Сейчас:** импортированная v0.3.0 EXPERIMENTAL, Python + Tkinter и Qt shell в Zone-теме для локального анализа, inventory search/filter, staged money/stack edits, immutable preview/local-copy apply, backup/hash browser с восстановлением в новую копию и Steam Cloud UI с явным connect/list/analyze/upload. U07 добавляет тёмную палитру, metadata/CRC badges, sidebar и snapshot-backed summary cards без новых runtime-зависимостей. B01 добавляет воспроизводимый PyInstaller builder для Linux `tar.gz`/`.deb` и Windows `zip`; локально подтверждён Linux bundle, Windows runner smoke ещё впереди. На Linux x86_64 доступен legacy `vendor/ooz.abi3.so`; на Windows x64 используется `pyooz==0.0.8`. Это исследовательская версия, не готовый универсальный редактор.

## Что доступно

- Чтение и изменение денег; изменение количества распознанных стаков с пересчётом веса.
- CRC32, распаковка Kraken, пересборка и побайтовая проверка round-trip.
- GUI для локальных файлов и Steam Cloud; CLI для исследования.
- Experimental: move, detach/deep detach, attach существующего orphan, raw patch и diff-record.
- Общий UI-free `EditorService` связывает parser, immutable preview, local export,
  backup restore и cloud transaction для Tk/CLI/Qt.
- Qt Cloud tab не вызывает helper при старте: сначала явное подключение и список
  `Data/*.sav`, затем анализ выбранного slot и upload только его preview.
- Qt shell использует визуальный референс Zone из U07: demo-данные макета не
  копируются, а badges/cards заполняются только после реального snapshot.

**Не реализовано как подтверждённые функции:** создание предмета по SID, клонирование, физическое удаление, прочность, attachments/upgrades, полные названия предметов. `detach` не означает физическое удаление.

Cloud-процесс использует fresh SHA, exclusive backup/recovery, persisted и
read-back; после WriteFile state machine различает `verified` и `uncertain` и
не повторяет upload автоматически. Worker lifecycle покрыт fake helper, но
работа с реальным Steam/GFN в этом репозитории ещё не проверена. Локальный
export использует общий backup/atomic path после S03. Остальные ограничения:
[состояние и пробелы](docs/STATUS.md).

## Запуск из исходников

Требуются Python 3.10+ и Tkinter; проверялся локальный x86_64 Linux, не все дистрибутивы.

```bash
sudo apt install python3 python3-tk
./run.sh
```

На Windows 11 x64 нужен Python 3.11+ с Tkinter; запусти `run.bat` из
папки проекта (или `py -3 app.py`). Native decoder ставится зависимостью
`pyooz==0.0.8`; Linux при отсутствии pip wheel использует bundled fallback.
При отсутствии execute-bit на Linux: `bash run.sh`. Steam нужен только для
cloud-режима. Helper устанавливается отдельно; старый локальный tar.gz не
является установленным приложением. Не выполняйте cloud-upload из
автоматических тестов.

Для нового Qt shell установи дополнительные зависимости и запусти модуль:

```bash
python3 -m pip install -r requirements-ui.txt
python3 -m ui
```

На Windows используй `py -3 -m pip install -r requirements-ui.txt` и
`py -3 -m ui`. В Qt shell можно искать и фильтровать локальный inventory,
застейджить подтверждённые money/stack изменения, нажать preview и сохранить
новую копию. На вкладке резервных копий видны hash/status журнала; проверенный
backup можно восстановить в новый путь, а исходный сейв и backup остаются
неизменными. На вкладке Steam Cloud upload показывает `verified` или `uncertain`;
после `WriteFile` автоматического повтора нет.

## Standalone-пакеты (B01)

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

## Пакеты и локальные материалы

[Исторические v0.1/v0.3 архивы](releases/legacy/) сохранены без изменения с [SHA256SUMS](releases/legacy/SHA256SUMS). Это исходники с Linux decoder, не самостоятельные `.exe`/AppImage. Будущие бинарные сборки публикуются в GitHub Releases после проверки на обеих ОС.

Исходные материалы владельца сохранены в `.local/original-import-2026-09-13/`, исключены из Git. Там находятся личные `.sav`, скриншоты, полный handoff, исходные архивы и manifest. При клонировании GitHub эти файлы не появятся; приложение и будущие синтетические тесты не должны от них зависеть.

## Лицензия

GPL-3.0, см. [LICENSE](LICENSE) и [зависимости](THIRD_PARTY_NOTICES.md). Игра, игровые ассеты и SteamCloudFileManager в дистрибутив приложения не включены. Проект не является официальным инструментом GSC или Valve.
