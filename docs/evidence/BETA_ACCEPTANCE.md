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
