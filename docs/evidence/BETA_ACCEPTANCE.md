# B02 beta acceptance matrix — current evidence

Дата отчёта: 2026-09-13. Source commit для локального package build:
`14650ce83e8e4519d771b36b14a02ce73fc09d5f`. Этот файл фиксирует проверенное
состояние и не превращает отсутствующие Windows/Steam данные в PASS. После
локальной UI-интеграции U07 Qt regression suite содержит 105 тестов; package
hashes ниже относятся к более раннему B01 source commit и не являются
артефактами U07.

## Матрица

| Gate | Linux x86_64 | Windows x64 | Evidence / причина |
|---|---|---|---|
| Source suite | **PASS** — 82 passed, 6 skipped | **NOT_RUN** | `python3 -m pytest tests -q`; optional Qt test module is skipped in the core environment; GitHub runner jobs не стартуют |
| Qt suite | **PASS** — 105 passed | **NOT_RUN** | `QT_QPA_PLATFORM=offscreen /tmp/save-editor-ui-venv/bin/python -m pytest tests -q` |
| U07 shell regression | **PASS** — 2 passed | **NOT_RUN** | Empty shell, sidebar navigation and snapshot-backed metadata; offscreen Linux |
| `make check` | **PASS** | **NOT_RUN** | Python 3.14.4 host; Windows command не выполнялся |
| Standalone build | **PASS** — tar.gz + `.deb` | **NOT_RUN** | B01 builder на Linux host; Windows должен собираться на Windows |
| Packaged `--help`/diagnostic | **PASS** | **NOT_RUN** | оба Linux executables exit 0, `decoder=loaded` |
| Packaged Qt startup | **PASS** — offscreen process alive | **NOT_RUN** | native desktop session/DPI ещё не проверены |
| Archive/package scan | **PASS** | **NOT_RUN** | нет `.sav`, `.bak`, `.local`, `.git`, credentials; manifest/vendor присутствуют |
| Local analyze/edit/export/restore из bundle | **NOT_RUN** | **NOT_RUN** | требуется manual clean-machine flow с disposable synthetic copy |
| DPI 100/150/200% и keyboard | **NOT_RUN** | **NOT_RUN** | offscreen test не заменяет native desktop QA |
| Steam helper connect/list/download | **NOT_RUN** | **NOT_RUN** | helper и Steam account не запускались |
| Cloud upload/persist/read-back | **NOT_RUN** | **NOT_RUN** | только fake transport tests; live upload требует отдельного поручения |
| Game/GFN load and re-save | **NOT_RUN** | **NOT_RUN** | игровой эксперимент не выполнялся |

## Артефакты локального Linux smoke

Команда:

```text
/tmp/save-editor-ui-venv/bin/python packaging/build.py --target linux \
  --output-dir /tmp/save-editor-b01-clean
```

Результат `exit 0`, `source_dirty=false` в `BUILD_MANIFEST.json`:

```text
# NOT RELEASE ASSETS: собраны Python 3.14.4 и host glibc, не build-lane 3.11
# на целевом runner-образе. Пригодны только как локальное smoke-evidence.
4d2a09381e044242d45f5cb16e0c04a23551ef6dbe33449d3e3daf72beafa580  SaveEditor-linux-x86_64-v0.3.0-experimental.tar.gz
7e5a5ce5356d62c65a694dbaaf802204417af9f7fe2917f7aef0d4e2f55d992b  stalker2-save-editor_0.3.0-experimental_amd64.deb
```

Дополнительно: `.deb` из этих артефактов объявлял `Depends: libc6 (>= 2.35)`
жёстко, независимо от build host. Это исправлено (минимум вычисляется из glibc
сборочной машины и пишется в `BUILD_MANIFEST.json` как `libc_minimum`), поэтому
пересобранный пакет даст другой hash.

Артефакты оставлены в `/tmp` и не коммитятся. Они собраны Python 3.14.4 и
текущим host glibc, поэтому не являются release assets для Ubuntu 22.04.

## Решение по выпуску

Текущий результат — **local-only experimental / release blocked**. Linux code и
bundle evidence полезны для следующего прогона, но cross-platform beta нельзя
объявлять до Windows build/smoke, target runner evidence и native DPI/keyboard
проверки. Cloud нельзя называть verified без tagged live helper run и
game/GFN reload/re-save. B02 не создаёт GitHub prerelease на этом состоянии.

## Обновление 2026-09-14 — гейты качества исходников

Изменения этого прохода не двигают release decision (она по-прежнему
`blocked`), но меняют то, что именно проверяется до релиза.

| Проверка | Результат | Команда |
|---|---|---|
| Source suite (core) | **PASS** — 113 passed, 10 skipped | `python3 -m pytest -q` |
| Qt suite | **PASS** — 132 passed | `QT_QPA_PLATFORM=offscreen .../python -m pytest tests -q` |
| Lint | **PASS** — clean | `python3 -m ruff check .` |
| Typecheck | **PASS** — 27 files | `python3 -m mypy` |
| Docs drift | **PASS** | `python3 tools/render_task_index.py --check` |
| Windows / runner / DPI / Steam / game | **NOT_RUN** | без изменений |

Закрытые в этом проходе дефекты, которых раньше не видел ни один gate:

- `steam_cloud.discover_helper` — re-export без теста: любое удаление «неиспользуемого»
  импорта ломало Tk GUI и Qt Cloud tab на старте. Теперь есть
  `tests/test_entrypoints.py`.
- CLI не имел ни одного теста и не импортировался (парсинг argv на уровне модуля).
  Теперь `cli.main(argv)` и `tests/test_cli.py`.
- Запрет «не грузить cloud из автотестов» существовал только текстом в README;
  теперь `SteamWorker` отказывает в `Connect`/`WriteFile` для app_id игры под
  pytest без `STALKER2_ALLOW_LIVE_CLOUD=1`.
- Метки runner в обоих workflow указывали на снятые с обслуживания образы —
  вероятная причина `startup_failure` без jobs.

### Известная нестабильность

`tests/test_ui_cloud.py::test_main_window_routes_cloud_snapshot_preview_to_upload`
однажды упал по `qtbot.waitSignal` timeout под параллельной нагрузкой и прошёл
в 10 последующих прогонах подряд, включая 6 прогонов на неизменённом `main`.
Это не регрессия текущего прохода, но перед release gate стоит завести карточку:
тест зависит от реальных QThread и 5-секундных таймаутов.

## Локальный Linux build 2026-09-14 (после гейтов качества)

Source commit `e1a1729ec16a1fbcb75a6b05de08328fa6e32f6f`, `source_dirty=false`,
сборка Python 3.14.4 / glibc 2.43.

```text
# NOT RELEASE ASSETS: build lane проекта — Python 3.11 на целевом runner-образе.
670abe74a91369bb139d025cb94be86b2f29ef9d4abdca6c38589913d8e4afcf  SaveEditor-linux-x86_64-v0.3.0-experimental.tar.gz
069c3d33278732b1d3ee119c3dc67838033fed916c72259e9243304c993a5b0d  stalker2-save-editor_0.3.0-experimental_amd64.deb
```

`.deb` теперь объявляет `Depends: libc6 (>= 2.43)` — фактический glibc сборочной
машины вместо прежней жёсткой 2.35; то же значение лежит в
`BUILD_MANIFEST.json` как `libc_minimum`. Размеры: 71 MiB tar.gz, 81 MiB deb.

| Проверка | Результат | Детали |
|---|---|---|
| Packaged diagnostic | **PASS** | exit 0, `decoder=loaded` из bundle, Qt 6.11.2 |
| Packaged `--help` | **PASS** | exit 0 |
| Packaged Qt startup | **PASS** | offscreen процесс жив 6 s, затем корректно снят |
| Local analyze/edit/export/restore **из исходников** | **PASS** | см. ниже |
| Local analyze/edit/export/restore **из bundle** | **NOT_RUN** | GUI не управляется headless; нужен ручной прогон |
| DPI 100/150/200 %, keyboard | **NOT_RUN** | offscreen не заменяет native desktop |
| Windows build / runner / Steam / game | **NOT_RUN** | без изменений |

Полный локальный цикл на synthetic save (не на личном сейве):

```text
before: money=100, inventory=2
edit:   money -> 900000, export в отдельный файл
source: SHA256 не изменился
backup: slot_<ts>_<uuid>_ORIGINAL.sav + journal
restore journal -> новый файл: байт-в-байт равен оригиналу
edited.sav сохраняет money=900000
```

### Найдено при сборке: требование к месту

Первая попытка сборки в `/tmp` (tmpfs 3.4 GiB) заполнила файловую систему на
стадии Debian staging и уронила окружение. Пик рабочего набора ≈1.7 GiB:
PyInstaller разворачивает Python и Qt, а `.deb` копирует это дерево ещё раз.
Прежняя диагностика — голый `shutil.Error` со списком путей. Теперь
`packaging/build.py` проверяет свободное место до старта и перехватывает сбой
staging с явным сообщением. Для CI это не блокер (hosted runner имеет десятки
GiB), для локальной сборки — да.

Release decision без изменений: **blocked** до Windows build/smoke, evidence
целевого runner и native DPI/keyboard.
