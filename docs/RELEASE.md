# Проверка и выпуск

## v0.5.15: Windows installer + portable и автообновление — 2026-09-20

Windows release-контур теперь публикует две разные сборки: Windows portable
`SaveEditor-windows-x86_64.zip` для запуска без установки и отдельный установщик
`SaveEditor-windows-x86_64-setup.exe` с ярлыком и обычной установкой. Linux сохраняет portable
tar.gz и отдельный системный `.deb`. GitHub Release и Cloudflare R2 получают
одинаковые итоговые байты; stable-имена, `latest.json` и `SHA256SUMS` создаются
из фактических файлов после сборки.

latest.json содержит версию, commit, target, размер и SHA-256 каждого файла.
Приложение проверяет manifest в фоне, показывает ручную кнопку проверки,
скачивает только разрешённый R2 host и перед заменой сверяет SHA-256. Portable
обновление применяет отдельный updater после закрытия GUI;
Windows installer и `.deb` открываются через системный установщик после
подтверждения пользователя. Невалидный manifest, сеть, размер или hash не
затрагивают текущую установку.

Локальная подготовка:

    make release-manifest ARTIFACT_DIR=release-input OUTPUT_DIR=release-output

Публикация и read-back:

    make r2-publish ARTIFACT_DIR=release-input OUTPUT_DIR=release-output

В CI tag-triggered job вызывает `tools/publish_release.py --publish-r2
--verify-r2`, прикрепляет два Windows варианта, Linux portable и `.deb` к
GitHub Release и проверяет все пять R2 object-ов через публичный Worker.
GitHub Actions source-test job остаётся без cloud credentials.

Релиз v0.5.15 фактически опубликован из commit
`7306dcbde417e9374038d9d9f47d198e4dfc2053`:
[GitHub Release v0.5.15](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.15).
Hosted run [35508107671](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35508107671)
подтвердил Windows installer smoke и Linux/Windows packaged smoke.
Worker версии `6075860d-b502-4ebe-b987-410a85bc51a8` задеплоен; пять
стабильных R2 object-ов загружены и прочитаны обратно через
`tools/publish_release.py --verify-r2`.

Фактические размеры и SHA-256 release/R2 assets: Windows ZIP — 61,985,583
bytes, `39b6479e2e8a85610d00af5695f4448b5008994a566102cf62aee81ff3f4bf9b`;
Windows installer — 38,187,197 bytes,
`54761d30ddb502c7b8c8a5dacb160a621030632a6a0e4dcac5bcfdb098b768dc`; Linux
portable tar.gz — 89,762,581 bytes,
`3bb8e1290d5642d935c6232df823937d2b7863495a0f3472c4a7b7c166bb89b7`;
Debian — 93,138,182 bytes,
`9fdc4a5a70d83c88d3f5f2a61f358662d5276f81bcab531ec9621fd3ce056ada`;
`latest.json` — 1,769 bytes,
`4bae8680c398acad8fb1bbbc65263ef4a716f8697762ae8a594d5af975511dd7`.
В репозитории пока нет `CLOUDFLARE_API_TOKEN` и
`CLOUDFLARE_ACCOUNT_ID`, поэтому автоматический release-job остановился на
deploy Worker; публикация этого релиза завершена локальным авторизованным
Wrangler и `gh` без сохранения OAuth-токена в GitHub Secrets.

## Непубликованный continuation — 2026-09-20

Добавлен read-only S2 catalog discovery для loose official/Zone Kit/Steam
Workshop CFG: реальные item/upgrade names и icon paths могут попасть в общий
каталог, Workshop overlay выбирается явно, а `.pak` и S2 save writer остаются
за evidence gate. Это изменение пока не является новым release/tag и не
подтверждает игровой load/re-save.

## Продолжение main — 2026-09-20

Коммит `0f9d207` продолжает v0.5.8 без поднятия версии: добавлены guarded
experimental S2 armor-condition reader/writer для подтверждённой
actor-owned брони, save-local names и icon resolution с официальными loose
ресурсами/безопасным fallback. Локальная проверка merged `main`: `496 passed`,
`make check`, packaged diagnostic с загруженным decoder.

Локальные Linux artifacts пересобраны и проверены через `dist/SHA256SUMS`:
`SaveEditor-linux-x86_64-v0.5.8.tar.gz` и
`stalker2-save-editor_0.5.8_amd64.deb`. Web опубликован из `main` на Pages:
[preview revision d555bfc9](https://d555bfc9.stalker-save-editor.pages.dev/);
preview и canonical URL отвечают HTTP 200. Это не новый GitHub tag/release.
Steam `WriteFile` пользовательского слота и игровой load/re-save здесь не
запускались.

## Выпуск v0.5.8 — Proton S2 discovery, Cloud URL refresh и явный upload

Этот проход закрывает четыре проблемы из пользовательского запуска:

- S.T.A.L.K.E.R. 2 на Linux/Proton ищется без текущего manifest-файла, включая
  legacy `Local Settings/Application Data` и вложенный `SaveGames/Data`;
- после анализа snapshot game picker синхронизируется с фактически найденным
  `format_id`, поэтому S2 больше не отображается как Shadow of Chernobyl;
- короткоживущий Steam web download URL обновляется при истечении срока;
- discovery-подсказки больше не используют `palette(mid)` на тёмном фоне, а
  cloud snapshot получает явную кнопку `Сохранить и загрузить в облако`.

Локальное доказательство: `442 passed`, `make check`; read-only live discovery
нашёл 53 локальных S2 slot-файла и 50 remote `Data/*.sav` через Steam Cloud web.
Тег `v0.5.8` указывает на `103ec666d091754024c2073d2e435f586cb4e688`.
Source CI [35446190978](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35446190978)
прошёл всеми четырьмя matrix jobs; standalone build
[35446471756](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35446471756)
прошёл Linux и Windows, включая packaged diagnostics. Релиз опубликован:
[GitHub Release v0.5.8](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.8).

Assets release: Linux portable, Debian amd64, Windows x64 и `SHA256SUMS`.
Хэши: Linux `12dc2d2602c24c4760ca5a96c23e0cb0821476b9ca2ac7755c88543cc7aaa8e7`,
Debian `a125a55c5b1bdad1ffef929333d7d9f06058f56fc3baa98b2ae84c89555c6c82`,
Windows `aec3e7ede72c01a16477e13587a298b74add288787073f0be8fa6b2701b2ea40`.
Эти же SHA256 получены при read-back трёх stable-файлов через Cloudflare
Worker: [Linux](https://save-editor-downloads.save-editor.workers.dev/SaveEditor-linux-x86_64.tar.gz),
[Windows](https://save-editor-downloads.save-editor.workers.dev/SaveEditor-windows-x86_64.zip),
[Debian](https://save-editor-downloads.save-editor.workers.dev/stalker2-save-editor_amd64.deb).
Pages повторно опубликован с revision `72b9aa0d`:
[stalker-save-editor.pages.dev](https://stalker-save-editor.pages.dev/) отдаёт
HTTP 200 и содержит все три stable download link.

Реальный `WriteFile` пользовательского слота, игровой load/re-save и системная
установка `.deb` с правами root в release gate не запускались: это отдельная
проверка владельца на резервной копии конкретного слота.

## Выпуск v0.5.7 — Steam Cloud web fallback и исправление game picker

Изменения этого прохода исправляют рассинхрон game picker и пустой список
Steam Cloud на сессиях, где `SteamAPI::GetFiles` возвращает `0`, хотя Steam
web/cache содержит сейвы. В transport добавлен read-only CDP fallback для
Steam Cloud web, локальный `remotecache.vdf` fallback и явная кнопка перезапуска
Steam с `-cef-enable-debugging`; запись остаётся через native Steam API и старую
fail-closed transaction.

Локальное доказательство: `439 passed`, `ruff`, `mypy`; live read-only smoke
получил 50 cloud slots и скачал один слот через Steam web. Live `WriteFile`
на пользовательский сейв намеренно не запускался. Tag-triggered CI и hashes
артефактов фиксируются в разделе фактической публикации после завершения
сборки.

## Выпуск v0.5.6

v0.5.6 закрывает зависание Steam Cloud, при котором `v0.5.4` останавливался
после загрузки `steamclient.so` и не возвращал управление Qt. Нативные
`init/connect/list/read/write` теперь выполняются в отдельном one-shot child
процессе; frozen bundle запускает отдельный console `SaveEditor-native`, parent
transport держит `Popen` handle и может убить child по hard timeout или при
закрытии окна. Bounded helper fallback выбирается только при первичном `list`.
После выбора транспорта автоматического переключения во время upload нет.

Tag `v0.5.5` был остановлен до GitHub Release после pre-release review: в нём
не было отдельного console child entrypoint для Windows и packaged smoke этого
пути. Пользовательский релиз — только v0.5.6 после corrective CI.

Перед публикацией обязательны: полный pytest, `make check`, tag-triggered
Linux/Windows standalone workflow, packaged diagnostic и smoke именно из
собранного Linux bundle. Реальный download/edit/upload пользовательского
сейва и game load/re-save в эти gates не входят.

### Фактическая публикация

Релиз опубликован 2026-09-19 из тега `v0.5.6`, указывающего на merge
`797884d9dcd372bc45e5b9a78ddd6f47590cc124`:
[GitHub Release v0.5.6](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.6).
Tag-triggered workflow
[35406902752](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35406902752)
завершил обе jobs со статусом PASS после повторного запуска Windows job:
Linux/Windows source tests, standalone build и packaged `SaveEditor-native`
smoke.

В этом разделе исторически зафиксирована публикация v0.5.6; актуальная
публикация v0.5.8 и read-back находятся выше.

## Выпуск v0.4.3

Выпуск v0.4.3 содержит Zone-библиотеку сохранений для всех четырёх
зарегистрированных игр, импорт внешнего файла без установленной игры и явный
вход в S.T.A.L.K.E.R. 2 Steam Cloud flow с helper. Локальный редактор и web
ядро используют прежние fail-closed backup, CRC/SHA и read-back проверки.
Повторная инициализация Qt-темы идемпотентна: приложение не выполняет второй
глобальный `Fusion`/stylesheet setup при создании окон.

Дополнительно в этом выпуске: S2 embedded inventory names, экспериментальный
money staging с явным предупреждением о границе игровой проверки, исправленные
карточки money/location/time и не сжимаемая раскладка inventory. Steam Cloud
helper остаётся внешней зависимостью; локальный helper smoke дал `Ping=PONG`,
`Connect=OK`, `GetFiles=0`, без записи.

Тег `v0.4.2` не был опубликован как GitHub Release: Linux standalone job
прошёл, а Windows source-test job завершился с `0xC0000409` во время закрытия
Qt worker. В `v0.4.3` добавлено ожидание worker перед закрытием окна и отдельный
регрессионный тест для этого жизненного цикла.

Release assets собраны tag-triggered workflow `standalone-build` на
`ubuntu-24.04` и `windows-2025`; к GitHub Release прикрепляются portable Linux
`.tar.gz`, Debian `.deb`, Windows `.zip` и platform-specific checksums.
Packaged diagnostic запущен на каждом runner до публикации артефакта. Реальный Steam upload,
игровая загрузка/re-save и runtime cloud без установленной игры остаются
отдельными внешними gates.

## Состояние публикации

В Git хранятся только исходники; исторические архивы удалены из дерева и
остаются в истории. GitHub Release `v0.4.3` опубликован после успешных Linux и
Windows jobs standalone workflow #35350988272 и содержит пять assets. Тег
указывает на merge `b4e789fe2a55a1779829483a2e95018f7ba19039`.

## Текущая CI pipeline (P03)

`.github/workflows/test.yml` уже описывает обязательную matrix
`ubuntu-24.04/windows-2025 × Python 3.11/3.12`. В каждой job включены только
`contents: read`, устанавливаются версии из `requirements.txt` и
`requirements-dev.txt`, проверяется чистый checkout без `.local`/сейвов,
запускаются compile и полный pytest suite. При сбое публикуются JUnit и
sanitized log; workflow не подключает Steam, credentials или cloud upload.
Приёмка P03 требует фактического PASS всех четырёх GitHub runner jobs и
сохранённого run URL; локальный Linux PASS сам по себе это не заменяет. PR #37
слит в `main`, но пять PR-run завершились `startup_failure` с нулём jobs;
issue #9 оставлена открытой до появления настоящего runner evidence.

## Pipeline B01/B02

1. Unit/behavior tests на Ubuntu 22.04 и Windows runner, Python 3.11/3.12. Synthetic fixtures, fake Steam worker, никаких credentials или live uploads.
2. Binary packaging на Python 3.11: Windows runner → zip с `SaveEditor.exe` и зависимостями; Ubuntu 22.04 runner → portable tar.gz и Debian/Ubuntu `.deb` с тем же bundled runtime. B01 уже добавляет PyInstaller onedir builder, отдельный diagnostic executable, deterministic archives, Debian staging через `dpkg-deb`, package scan и checksums. Onefile/AppImage/installer — отдельные задачи при необходимости. U05/U06 входят в packaged UI; clean-machine и Windows smoke ещё не доказаны.
3. Runtime dependency policy: ядро и storage остаются на стандартной библиотеке; `pyooz==0.0.8` и Qt/PySide6 вкладываются в standalone bundle, pytest и PyInstaller остаются build/dev-only. Native decoder/helper имеют pinned versions, source/license notices и SHA; helper отдельно до проверки его redistribution/ABI/protocol.
4. Smoke запуск CLI и Qt из артефакта вне checkout: unicode/space path, no Python installed, missing helper, no Steam. Display tests выполняются на реальной desktop-сессии; offscreen CI не заменяет DPI/manual QA.
5. SHA256SUMS, source commit/tag, dependency lock + source bundle, OS/architecture/minimum runtime, test evidence. Source/binary archives не включают .local, saves, .git или credentials.
6. Создать GitHub prerelease только после успешных обязательных gates. Бинарники прикрепляются к Releases; `dist/` не коммитится. Signed Windows installer требует предоставленного владельцем certificate; без него обозначить unsigned, не заявлять подпись.

Версии инструментов упаковки и Qt фиксировать в B01 после успешного smoke test, не устанавливать latest при каждой сборке. PyInstaller не cross-compiler; Linux CI не производит проверенный Windows exe. `.deb` не отменяет отдельную проверку glibc/архитектуры; portable tar.gz остаётся fallback для других Linux. Источник: [официальная документация PyInstaller](https://www.pyinstaller.org/en/stable/) и `dpkg-deb` из Debian toolchain.

## Матрица приёмки B02

| Проверка | Linux | Windows | Условие |
|---|---|---|---|
| Unit + fake-worker tests | обязательно | обязательно | exit 0, без network writes |
| Packaged startup без Python | обязательно | обязательно | native desktop |
| Local analyze/edit/export/restore | обязательно | обязательно | backup и before/after hashes |
| CRC/round-trip отказ на повреждённом файле | обязательно | обязательно | output не появляется |
| UI 1366×768, 150/200% DPI, keyboard | обязательно | обязательно | нет недоступных кнопок |
| Steam helper connect/list/download | обязательно для cloud claim | обязательно для cloud claim | pinned helper |
| Live upload/persist/read-back/GFN load/re-save | только по поручению владельца | только по поручению владельца | disposable slot, game build записан |

## Снимок B02 на 2026-09-13

Код B01 принят через [PR #44](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/44),
merge `3346167`. Linux bundle smoke на локальном x86_64 host PASS; точные
hashes и NOT_RUN строки находятся в
[`docs/evidence/BETA_ACCEPTANCE.md`](evidence/BETA_ACCEPTANCE.md). Windows
build, target runner, native DPI/keyboard, Steam helper и game/GFN reload пока
не доказаны, поэтому GitHub prerelease не создаётся.

При отсутствии live cloud evidence можно выпустить обозначенную local-only experimental beta с отключённым или явно непроверенным cloud path; нельзя маркировать cloud verified. При отсутствии Windows evidence не объявлять cross-platform beta завершённой.

## Формат evidence

Commit/tag, UTC date, OS/build/arch, Python и dependency lock hash, command, exit code, result artifact SHA, fixture/corpus ID, expected/actual, limitations. Для игровых опытов дополнительно game version, source/output/resaved hashes, exact handle/operation, menu/load/result/re-save. Данные приватных сейвов остаются локально.
