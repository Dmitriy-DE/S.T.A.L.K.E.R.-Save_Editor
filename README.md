# S.T.A.L.K.E.R. 2 HoC — Save Editor

Локальный редактор сохранений с подключением Steam Cloud для игры через GeForce NOW.

**Сейчас:** импортированная v0.3.0 EXPERIMENTAL, Python + Tkinter и Qt shell для локального анализа, inventory search/filter и staged изменения количества распознанных стаков, platform-aware decoder loader. На Linux x86_64 доступен legacy `vendor/ooz.abi3.so`; на Windows x64 используется установленный `pyooz==0.0.8`. Это исследовательская версия, не готовый универсальный редактор: preview/apply, standalone Windows build и реальный Windows smoke ещё впереди.

## Что доступно

- Чтение и изменение денег; изменение количества распознанных стаков с пересчётом веса.
- CRC32, распаковка Kraken, пересборка и побайтовая проверка round-trip.
- GUI для локальных файлов и Steam Cloud; CLI для исследования.
- Experimental: move, detach/deep detach, attach существующего orphan, raw patch и diff-record.
- Общий UI-free `EditorService` связывает parser, immutable preview, local export и cloud transaction для Tk/CLI и будущего Qt.

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
`py -3 -m ui`. В Qt shell можно искать и фильтровать локальный inventory и
застейджить количество подтверждённого stack; bytes сейва не меняются до
preview/apply в U04.

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
