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
4d2a09381e044242d45f5cb16e0c04a23551ef6dbe33449d3e3daf72beafa580  SaveEditor-linux-x86_64-v0.3.0-experimental.tar.gz
7e5a5ce5356d62c65a694dbaaf802204417af9f7fe2917f7aef0d4e2f55d992b  stalker2-save-editor_0.3.0-experimental_amd64.deb
```

Артефакты оставлены в `/tmp` и не коммитятся. Они собраны Python 3.14.4 и
текущим host glibc, поэтому не являются release assets для Ubuntu 22.04.

## Решение по выпуску

Текущий результат — **local-only experimental / release blocked**. Linux code и
bundle evidence полезны для следующего прогона, но cross-platform beta нельзя
объявлять до Windows build/smoke, target runner evidence и native DPI/keyboard
проверки. Cloud нельзя называть verified без tagged live helper run и
game/GFN reload/re-save. B02 не создаёт GitHub prerelease на этом состоянии.
