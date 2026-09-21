# Проверка и выпуск

## v0.5.18 — Steam Cloud provenance, diagnostics and OTA correction — 2026-09-21

The Cloud tab now preserves the discovery backend for every row. Steam cache
metadata is never routed into native `FileRead`; a matching local cache copy is
read locally, available web data is read through CDP, and unavailable metadata
fails with a precise read-only diagnostic. The table displays the source so
`Persisted: нет` is not mistaken for “not in Steam Cloud”.

The application writes bounded rotating logs and adds **Отправить логи**. The
existing R2 Worker accepts only bounded gzip diagnostics, stores them under a
random key, never exposes a read route, and cleans objects older than 30 days.

The updater checks the Linux package root before the generic manifest, selects
the `.deb` artifact for installed package builds, and launches an explicit
`pkexec apt-get`/`xdg-open` handoff after size and SHA-256 verification. Windows
installer and portable replacement remain separate. A handoff is reported as
pending until the operating system/package manager completes it.

The implementation and local gate are recorded in
[`evidence/CLOUD_DIAGNOSTICS_OTA_2026-09-21.md`](evidence/CLOUD_DIAGNOSTICS_OTA_2026-09-21.md).

## v0.5.17 — fail-closed Cloud/update/publication hardening — 2026-09-20

Релиз v0.5.17 делает write capability явной во всём Steam Cloud flow:
native/helper допускают upload, а web/CDP/cache используются только для
list/download. До вызова `WriteFile` отказ однозначный; после потенциальной
записи ошибка остаётся `uncertain` и не повторяется автоматически.

Updater блокирует недоверенный redirect до сетевого запроса и отделяет rollback
замены от best-effort удаления backup. Browser начинает четыре независимые
core-загрузки параллельно и не анализирует файл до завершения фоновой установки
каталога.

Tag workflow теперь fail-closed: без любого Cloudflare secret GitHub Release не
создаётся. Stable directory строится один раз; Worker deploy, шесть R2 objects с
публичным read-back и GitHub assets используют один набор байтов. Локальные и
hosted доказательства перечислены в
[`evidence/HARDENING_0.5.17_2026-09-20.md`](evidence/HARDENING_0.5.17_2026-09-20.md).

S2 condition writer по-прежнему ограничен подтверждённым equipped-armour
anchor. Weapon/helmet condition, произвольные S2 add/upgrades, Enhanced Edition
parser, live Steam upload и game load/re-save не объявляются готовыми без
контролируемых данных.

### Фактическая публикация

Релиз собран и опубликован из чистого commit
`639557bc656e40681b63e4edf848c12fce7068e9`. Hosted source matrix
[35538975049](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35538975049)
прошла на Ubuntu 3.11/3.12 и Windows 3.11/3.12. Hosted package matrix
[35539090000](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35539090000)
прошла на Linux и Windows, включая smoke Windows installer.

Финальный release job остановился до публикации на fail-closed проверке:
GitHub repository не содержит `CLOUDFLARE_API_TOKEN` и
`CLOUDFLARE_ACCOUNT_ID`. Поэтому публикация сделана после успешных package
jobs локальным авторизованным Wrangler/`gh` из того же подготовленного набора.
Worker version — `e9b23133-910d-4d73-9ab7-8933cbac041a`; шесть R2 objects
прочитаны обратно через публичный Worker и совпали с локальными байтами.
[GitHub Release v0.5.17](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.17)
содержит Windows portable/installer, Linux portable, `.deb`, `latest.json` и
`SHA256SUMS`. Pages deployment
[`7e3cd3e8`](https://7e3cd3e8.stalker-save-editor.pages.dev/) опубликован;
canonical URL отвечает HTTP 200.

Финальные SHA-256: Windows portable
`e62ac213394b817250ede47eec67ca48179189c612f1c7824778e57e1eb31e8b`, Windows
installer `6554147ac2299d2a11edf6d3ac36d118bbe5d8b9015047a86faf46d17aada64b`,
Linux portable `ea1547e591ff78eafc8629c00acaddcae489b7538ea89fdab116c25a5d4c8f4a`,
Debian `863b7d0c3a96a3def35b41ef7fa2ff7b2a1f9831eedf6a518b7bf36b9378e987`.

## v0.5.16 — bounded equipment protocol, release-aware Steam Cloud и UX — 2026-09-20

Этот релиз-кандидат объединяет continuation по issues #95–#99: bounded
condition/upgrades/placement protocol для контролируемой проверки, семь
release-aware Steam Cloud profiles с app ID/path/backend diagnostics, безопасное
определение Enhanced Edition без подмены формата оригинальным X-Ray parser и
автоматический preview перед web-download. Backup, fresh SHA, atomic export,
CRC/Kraken round-trip и fail-closed cloud transaction сохранены.

Локальный gate: `make check`, полный `make test` — `547 passed`, focused
Qt/web/cloud — `54 passed`. Linux portable и `.deb` собраны из `0.5.16` и
проверены packaged diagnostic; Windows portable и installer собираются только
на Windows runner. Реальный Steam Cloud upload и game load/re-save не входят в
автоматический gate.

Тег `v0.5.16` указывает на чистый commit
`c47e62d509467b9caaed092994edbae4e02352ae`. Hosted run
[35514835825](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35514835825)
прошёл Linux и Windows source tests, packaging, portable diagnostics и
Windows installer smoke. Его release-job остановился на Worker deploy из-за
пустых `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID`; GitHub Release и R2 затем
завершены теми же CI artifacts через авторизованный локальный Wrangler.

Релиз: [GitHub Release v0.5.16](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.16).
Worker version `b5ba5517-a3a8-45d0-bc9a-a8cace7e64ad`; пять stable R2 объектов
прочитаны обратно через public Worker и совпали с локальными байтами.
Pages preview [fdd869f5](https://fdd869f5.stalker-save-editor.pages.dev/) и
[canonical URL](https://stalker-save-editor.pages.dev/) отвечают HTTP 200;
страница содержит отдельные Windows installer и portable links.

Фактические размеры и SHA-256: Windows ZIP — 62,013,435 bytes,
`15a0234fc806ade556a9d630261008bc06a6c0db29d07aad13c502560b2dadd7`;
Windows installer — 38,192,590 bytes,
`a06068bec04895e2a6d5bf1f4c52257278080312e6dbf307054c0eb9f9261f06`;
Linux portable — 89,804,743 bytes,
`0f278378b780f2f137513c11bcdf73f81f12a9298e9509a3d18b228bbdc492b0`;
Debian — 93,129,042 bytes,
`cb492a4cb94f1848cc9de9de33780ce011f374a36b2857c48077a15eacc34937`.

Для будущих tag releases workflow сначала создаёт GitHub assets, а Worker/R2
публикует только при наличии обоих secrets и иначе выдаёт явное warning; это не
теряет уже собранный GitHub Release из-за внешней Cloudflare credentials.

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
