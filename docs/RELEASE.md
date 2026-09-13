# Проверка и выпуск

## Что опубликовано сейчас

В Git хранятся исходники и неизменённые исторические пакеты releases/legacy. Standalone Windows/Linux beta ещё не собрана. Версия runtime остаётся 0.3.0-experimental; изменение документации не повышает её до готовой beta.

## Текущая CI pipeline (P03)

`.github/workflows/test.yml` уже описывает обязательную matrix
`ubuntu-22.04/windows-2022 × Python 3.11/3.12`. В каждой job включены только
`contents: read`, устанавливаются версии из `requirements.txt` и
`requirements-dev.txt`, проверяется чистый checkout без `.local`/сейвов,
запускаются compile и полный pytest suite. При сбое публикуются JUnit и
sanitized log; workflow не подключает Steam, credentials или cloud upload.
Приёмка P03 требует фактического PASS всех четырёх GitHub runner jobs и
сохранённого run URL; локальный Linux PASS сам по себе это не заменяет. PR #37
слит в `main`, но четыре PR-run завершились `startup_failure` с нулём jobs;
issue #9 оставлена открытой до появления настоящего runner evidence.

## Будущая pipeline (B01, B02)

1. Unit/behavior tests на Ubuntu 22.04 и Windows runner, Python 3.11/3.12. Synthetic fixtures, fake Steam worker, никаких credentials или live uploads.
2. Binary packaging на Python 3.11: Windows runner → zip с `SaveEditor.exe` и зависимостями; Ubuntu 22.04 runner → portable tar.gz и Debian/Ubuntu `.deb` с тем же bundled runtime. Первым использовать PyInstaller onedir; `.deb` собирать через `dpkg-deb` из staging tree, onefile/AppImage/installer — только отдельной задачей при необходимости.
3. Runtime dependency policy: ядро и storage остаются на стандартной библиотеке; `pyooz==0.0.8` и Qt/PySide6 вкладываются в standalone bundle, pytest остаётся dev-only. Native decoder/helper имеют pinned versions, source/license notices и SHA; helper отдельно до проверки его redistribution/ABI/protocol.
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

При отсутствии live cloud evidence можно выпустить обозначенную local-only experimental beta с отключённым или явно непроверенным cloud path; нельзя маркировать cloud verified. При отсутствии Windows evidence не объявлять cross-platform beta завершённой.

## Формат evidence

Commit/tag, UTC date, OS/build/arch, Python и dependency lock hash, command, exit code, result artifact SHA, fixture/corpus ID, expected/actual, limitations. Для игровых опытов дополнительно game version, source/output/resaved hashes, exact handle/operation, menu/load/result/re-save. Данные приватных сейвов остаются локально.
