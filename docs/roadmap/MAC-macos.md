# MAC — macOS на текущем стеке

**Факты.**

- `packaging/build.py`: `SUPPORTED_TARGETS = {"linux","windows"}` — ограничение наше, не технологическое.
- У `pyooz 0.0.8` есть колесо `macosx_10_9_universal2`.
- Энкодер Kraken (`tools/build_ooz_encoder.py`) собирается из исходников и нужен для записи S2.
- Игр под macOS нет, поэтому сценарий на Mac: сейвы из Steam Cloud, сейвы из CrossOver или Whisky, файлы, скопированные с ПК.

## MAC-1 — Сборка `.app`

**Кто:** Codex · **Размер:** M · **Уровень:** L3

**Шаги.**

1. `packaging/build.py`: цель `macos`, PyInstaller `BUNDLE` → `SaveEditor.app`. Сначала arm64, universal2 отдельной задачей.
2. `packaging/editor.spec`:
   - datas как для Linux, без `vendor/`;
   - иконка `.icns` генерируется из `assets/app_icon_256.png`;
   - `Info.plist`: имя, версия, ассоциация `.sav`/`.scop` только на чтение.
3. Энкодер Kraken под macOS через `tools/build_ooz_encoder.py`. Если не собирается — S2 на Mac только чтение, и Doctor это показывает.
4. `editor/platforms.py`:
   - пути данных `~/Library/Application Support/Stalker2SaveEditor`;
   - `libsteam_api.dylib` (из Steam.app или рядом с приложением);
   - поиск сейвов в префиксах CrossOver и Whisky — только чтение путей.
5. Дочерние процессы (`ui/worker_process.py`): внутри `.app` использовать `sys.executable`.

**Приёмка.** `python packaging/build.py --target macos --output-dir dist` на macOS-раннере собирает `.app`; `SaveEditor.app/Contents/MacOS/SaveEditor --diagnostic` отвечает.

## MAC-2 — CI macos-14

**Кто:** Codex · **Размер:** S · **Зависит:** MAC-1 · **Уровень:** L3

**Шаги.**

1. Джоба `package-macos` в `build.yml` на `macos-14`.
2. Сборка и smoke `--diagnostic` + `--peek` на фикстуре.
3. `zip` и `.dmg` (`hdiutil`), артефакт.
4. На тегах — в Release (через ST-8).

## MAC-3 — Подпись и обновления

**Кто:** Codex · **Размер:** M · **Зависит:** MAC-2, D7 · **Уровень:** L4

**Шаги.**

1. Ad-hoc подпись: `codesign -s -`.
2. Нотаризация — по решению D7.
3. Updater для macOS: скачать `.dmg`, проверить sha256, открыть и показать инструкцию. Не заявлять «обновлено», пока версия не подтверждена.

## MAC-4 — Проверка на реальном Mac (владелец)

- Есть ли у владельца Mac или доступ к нему? Без этого macOS — только L3 из CI.
- Сценарий: открыть скачанный сейв S2 и сейв ЗП, поменять деньги, экспортировать, облако.
