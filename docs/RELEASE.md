# Проверка и выпуск

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
