# Проверка и выпуск

## v0.7.2 — официальные названия, звуки из игры, слоты по играм — 2026-09-25

Тег `v0.7.2` на commit `860ebe3` (PR #139, изменения — #136, #137, #138).
Tagged workflow собрал Linux и Windows (source gate, portable/Debian,
Windows portable/installer — success); job публикации остановился на
отсутствии Cloudflare-секретов, байты CI опубликованы вручную
(`publish_release.py --publish-r2 --verify-r2`, `gh release create`). Все
четыре ссылки `releases/latest/download/…` скачаны заново и совпали с
`SHA256SUMS`; `latest.json` = `0.7.2`.

Веб: первый деплой v0.7.2 не стартовал (`editor/xray_slots.py` не попал в
`tools/build_web_bundle.py`); исправлено в #140 вместе с тестом на полноту
бандла, передеплоено, страница стартует и грузит `catalog_names.json`.
Десктопные пакеты это не затрагивало.

- `SaveEditor-windows-x86_64.zip` — `76a259656367acee0641e315dc147ff3f11c9170a5d6fba574ab846e93306a15`
- `SaveEditor-windows-x86_64-setup.exe` — `c1a9d30c71dc51c555509005e9e7d09139058a2f83ddd374ea520fe3b3fbb33e`
- `SaveEditor-linux-x86_64.tar.gz` — `0b03f4df189f33cb88cb731e8cc6e5159d931657866be23e05bd9e5d690b12f3`
- `stalker2-save-editor_amd64.deb` — `c633eba35f871f173bc7d4f690289ea7ad7e69f07057809d69af9bb9cb94f665`

## v0.7.1 — правильные имена S2, названия и апгрейды трилогии — 2026-09-25

Тег `v0.7.1` на commit `80f2ee6` (PR #133). Tagged workflow собрал Linux и Windows
(source gate, portable/Debian, Windows portable/installer — success); job
публикации остановился, как и раньше, на отсутствии Cloudflare-секретов.
CI-байты опубликованы вручную (`publish_release.py --publish-r2 --verify-r2`,
`gh release create`). Все четыре ссылки `releases/latest/download/…` скачаны
заново и совпали с `SHA256SUMS`; `latest.json` = `0.7.1`. Веб задеплоен и
стартует без ошибок.

- `SaveEditor-windows-x86_64.zip` — `b23f313631b43841f99048695a2f0d27f70324ea724f4cdfbbd42115d772cd46`
- `SaveEditor-windows-x86_64-setup.exe` — `522c5a8b96b95d25b1859cce3ef9d07aa46061c23365e7021b20d76dc614f7eb`
- `SaveEditor-linux-x86_64.tar.gz` — `a329b7295e82129ce9ef5bd0dfa34af13b19f27c66b665523ac3e3f92760905f`
- `stalker2-save-editor_amd64.deb` — `cf04be9e646f071b0310bdf4899bfb16f0cbf8636a5215cbae37726d9d34223b`

## v0.7.0 — языки, карточки сейвов, звук и анимации — 2026-09-25

Тег `v0.7.0` на commit `210c744` (PR #131). Tagged workflow
[#36089886149](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/36089886149)
прошёл source gate, Linux portable/`.deb` и Windows portable/installer.
Release job, как и раньше, остановился на отсутствующих secrets; те же
CI-байты опубликованы вручную (`publish_release.py --publish-r2 --verify-r2`,
`gh release create`). Все четыре ссылки `releases/latest/download/…` скачаны
заново и совпали с `SHA256SUMS`; `latest.json` = `0.7.0`. Веб задеплоен и
проверен в английской локали. Сборки выросли на ~10–15 МБ из-за Qt Multimedia
(звуки интерфейса).

| Файл | Размер | SHA-256 |
|---|---:|---|
| `SaveEditor-windows-x86_64.zip` | 74,048,955 | `c6c7c75e685ee0a03e356b3a2d5678664494dad5d7cead1fc5fd72db48ce5be0` |
| `SaveEditor-windows-x86_64-setup.exe` | 46,464,769 | `67318920beb334d66d59f382b66e9dff452f482bf2d9d7e7fc51cfedab29a164` |
| `SaveEditor-linux-x86_64.tar.gz` | 91,997,550 | `124ebcfb3882f494ffdab47577827650e635bc13f2afcda7d361a3a3b16ea6b5` |
| `stalker2-save-editor_amd64.deb` | 102,880,618 | `aad803bc0223c9613a1e70a9ab4c7332e91c69a1aef3560ff00cf7d7615d9741` |

## v0.6.0 — канонический редизайн — 2026-09-25

Тег `v0.6.0` на commit `4256879` (main после PR #127, #128, #129). Tagged
workflow [#36069147209](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/36069147209)
прошёл source gate, Linux portable/`.deb` (glibc 2.35, lintian) и Windows
portable/installer smoke. Первая попытка тега остановилась на lintian
`duplicate-font-file` (встроенный Liberation Sans Narrow) — добавлен
обоснованный override (#129), неопубликованный тег перенесён.

Release job, как и раньше, остановился на отсутствующих `CLOUDFLARE_*`/
`APT_SIGNING_*` secrets. Те же CI-байты опубликованы вручную:
`tools/publish_release.py --publish-r2 --verify-r2` (R2 read-back через
публичный Worker, `latest.json` = `0.6.0`, commit `4256879`) и
`gh release create`. Все четыре публичные ссылки `releases/latest/download/…`
скачаны заново и совпали с `SHA256SUMS`. APT не публиковался (исходный ключ
утерян). Веб-версия задеплоена на Cloudflare Pages и показывает v0.6.0.

| Файл | Размер | SHA-256 |
|---|---:|---|
| `SaveEditor-windows-x86_64.zip` | 63,673,462 | `60f3198c237c60dae0e10a6e5f8ebbc3083947ee454cfebaf74e1368545a8fc3` |
| `SaveEditor-windows-x86_64-setup.exe` | 39,064,520 | `4c1756cd18a2d7810a1a6bc030c8b28eea1b649870380fa7669e59e7d790ac75` |
| `SaveEditor-linux-x86_64.tar.gz` | 81,518,395 | `7c6f1778c8800ac4237e3adacd08f2cffa84cacf54c77e7c292230f209ddd3ee` |
| `stalker2-save-editor_amd64.deb` | 86,265,680 | `26c9c1464c9ec38a43dcfd0f65445fb62817256f9d42aa6198f29c9070c3ac8e` |

## v0.5.21 — published root release; APT pending key recovery — 2026-09-22

Публичный root-релиз завершён из commit
`86cd76e3fb44c93249cb31f2da59ad204d4660e5` после PR
[#121](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/121),
[#122](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/122),
[#123](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/123) и
[#124](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/124).
Tagged workflow
[#35787422476](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35787422476)
прошёл source gate, Linux portable/`.deb` и Windows portable/installer smoke.
Публичные GitHub/R2 assets затем были опубликованы из тех же CI-байтов и
прочитаны обратно побайтно.

Изменения релиза исправляют ручной сценарий пользователя без
подмены результата за публичный релиз:

- S2 больше не показывает неподтверждённый X-Ray faction editor;
- отдельный каталог Zone Kit/Workshop подключается через Settings или
  автопоиск, показывает локализованные CFG names и loose icons, но остаётся
  read-only и не разрешает добавление предметов по неподтверждённому SID;
- Cloud upload сохраняет исходный Steam `Data/<slot>.sav` locator и отклоняет
  `-edited.sav`/`.edited.sav` artifacts;
- изменённый compact S2 payload повторно кодируется обязательным bundled
  Kraken encoder и проверяется CRC, decompression и round-trip до `WriteFile`;
- при отсутствии encoder операция сохранения завершается с ошибкой и не создаёт
  раздутый stored-block fallback вместо compact сейва;
- rotating diagnostics уже отправляются через существующий R2 endpoint, но
  этот проход не публикует новый tag и не выполняет live write в Steam.
- S2 weapon condition использует общий структурный codec для всех принятых
  actor-owned weapon rows с точным anchor; названия Kharod/Lavina/Skif в
  evidence — наблюдаемые примеры, а не ограничительный список.

Local source gate after the final fixes: `669 passed`, 9 Node tests, Ruff,
mypy, generated web/theme checks and `git diff --check` pass. The packaged
artifacts were built by the tagged workflow from the exact release commit;
the local dirty checkout was not used as a release source.

GitHub Release
[v0.5.21](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.21)
and the R2
[`latest.json`](https://save-editor-downloads.save-editor.workers.dev/latest.json)
contain the same four packages, `SHA256SUMS` and OTA manifest. Every public
GitHub and R2 download was read back and matched the local CI hashes and sizes.
The direct `.deb` is published; the signed APT channel remains unavailable
until the original private signing key is recovered. A replacement key must
not be generated for the existing channel.

## Diagnostics infrastructure

`POST /diagnostics` принимает только bounded `application/gzip` payloads. The
Worker requires its `DIAGNOSTICS_RATE_LIMITER` binding and returns `429` when
the Cloudflare rate limit is exceeded; it returns `503` rather than accepting
unbounded traffic when the binding is absent. Diagnostics objects are never
served through the public download route.

Retention is configured outside the request path with
[`infra/downloads-worker/lifecycle.json`](../infra/downloads-worker/lifecycle.json):
objects under `diagnostics/` expire after 30 days. Deploy/update the Worker and
bucket policy together:

    npx --yes wrangler@4 deploy --config infra/downloads-worker/wrangler.toml
    npx --yes wrangler@4 r2 bucket lifecycle set save-editor-downloads \
      --file infra/downloads-worker/lifecycle.json --force

The tag workflow applies both steps before publishing release assets. The
diagnostics client contains no authentication secret; Cloudflare-side rate
limiting is the abuse-control boundary.

## Current next-tag distribution contract

The next public tag uses one source gate followed by native Linux and Windows
package jobs. Linux packaging runs in an Ubuntu 22.04-compatible container and
must pass the declared glibc 2.35 floor; the Debian package is checked by
`dpkg-deb`, strict offline AppStream validation and lintian. Lintian `E:` and
`W:` findings block the job, while `I:` and `P:` findings are reported as
non-fatal informational output.

The release job requires Cloudflare credentials and an APT signing key before
it deploys the Worker or writes R2. It prepares the stable root assets once,
builds `release-output/apt/` with `dists/stable`, `pool/`, `Packages.gz`,
`InRelease`, `Release.gpg` and `repository-key.asc`, then uploads package bytes
before indexes and the signed `InRelease` before `latest.json`. Every root and
APT object is read back through the public Worker. A disposable source then
runs `apt update`, discovers the tagged package and downloads that exact
version. Only after those checks does the workflow create/update GitHub Release.

Direct Windows installer/portable, Linux portable and `.deb` assets remain
available; APT is an additional Linux installation/update channel. The exact
commands and secret names are maintained in [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## v0.5.20 — native writer for remote-only Steam Cloud listings — 2026-09-21

Steam `GetFileCount()` returns the files currently synchronized into the local
RemoteStorage view; it is not a complete remote web listing. When that count is
zero, the desktop transport may still obtain the selected `Data/*.sav` from
Steam Cloud web or `remotecache.vdf`, while retaining the successfully
initialized native `FileWrite` capability for upload. A transport with only web
or cache access and no native/helper writer remains read-only.

The regression is covered by native subprocess tests for both web and cache
listings. Local verification passed with `601 passed` and `make check`. A live
read-only smoke on the current Steam session found `52` cache entries and
reported `writable=True`; a real write to a user slot and in-game load/re-save
were intentionally not performed, so they remain external runtime gates.

Standalone package run
[35638429573](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35638429573)
прошёл source gate, Linux portable/`.deb` и Windows portable/installer smoke.
Release job остановился до внешних мутаций на отсутствующих secrets
`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `APT_SIGNING_KEY` и
`APT_SIGNING_KEY_ID`. Шесть root-ассетов поэтому вручную опубликованы
авторизованными `gh` и Wrangler из merge commit
`1adb396b8ddcc4ffb3c4f566c32560726ce5ea55`:
[GitHub Release v0.5.20](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.20)
и [R2 latest.json](https://save-editor-downloads.save-editor.workers.dev/latest.json).
Все GitHub download и R2 read-back совпали с локальными файлами побайтно.
APT не изменялся из-за отсутствия исходного приватного signing key.

SHA-256 бинарных ассетов: Windows portable
`f3d21583c8999a8d84283684a5ff45d20b105bc9bf538e59f6d22edee372d3ba`, Windows
installer `64e1ee9da8622449f42c41aaaadbccfd2722c04df07161c4eac1b5ef537109a5`,
Linux portable `82b7dfa49d00464a4bf3e5180a1fceafa457176e87d6850861b71ac15a03ede0`,
Debian `7c6c05f762f9adf2c2fa35f2b9b58c346b119e76eb6adca39b2d8d0a492e97bb`.

## v0.5.19 — one-click desktop save flow — 2026-09-21

Desktop save теперь сводится к одной понятной операции: после редактирования
нажать **Сохранить**, подтвердить один popup, и приложение само делает
внутренний preview, проверяет fresh SHA/CRC, создаёт verified backup и атомарно
заменяет открытый локальный слот. Три ручные вкладки/этапа больше не требуются;
журнал изменений и backups сохранены для аудита и восстановления. Steam Cloud
остаётся отдельным явным upload flow с теми же safety checks.

PR [#104](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/104)
слит в `main`. Локальная проверка — `575 passed` и `make check`. Source matrix
[35587937545](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35587937545)
прошла на Ubuntu/Windows для Python 3.11/3.12. Standalone package run
[35588193488](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35588193488)
прошёл Linux/Windows сборку и smoke; его release job корректно остановился до
публикации из-за отсутствующих repository secrets Cloudflare.

Релиз опубликован из merge commit
`f44377d12da5d78c24c1afb3b5acf78e8b906a74`: [GitHub Release v0.5.19](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.19).
Worker version — `52856335-1c63-450f-9183-50a1a7ee8e56`; R2 objects загружены
авторизованным Wrangler, затем все шесть файлов прочитаны через публичный Worker
и сравнены побайтно. `latest.json` указывает версию `0.5.19`, source commit и
раздельные Windows installer/portable targets.

После финальной проверки `main` (`e11f469a8bc6df8b2980db765f635cb53fe4ac3c`)
тот же `v0.5.19` был вручную обновлён из standalone run
[35623997966](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35623997966):
шесть root-assets заменены в R2 авторизованным Wrangler и в GitHub Release
через `gh`. Тег не переписывался; `latest.json` явно содержит source commit
этого проверенного набора. APT-репозиторий не изменялся: для его публикации
нужен исходный приватный signing key.

SHA-256 и размеры release/R2 assets:

- Windows portable — 62,315,347 bytes,
  `77989c6696c220744ada8afb4c0d57a6ecf8f698c5bbab4c7fb5c1a13014b3f8`;
- Windows installer — 38,264,578 bytes,
  `66c9feef9c1e806b0a0e3145dd8fe8f678827fe884c5381054346f46c5cbfccf`;
- Linux portable — 79,239,602 bytes,
  `9e1633d771da6c724cdd55bb383264e589d2c68613b01385e2ae22674af1a157`;
- Debian — 85,215,576 bytes,
  `d2c29f987a6b96e0dbf605850a84db09e96a285fce0ee8ea2a270dbe10e2456b`.

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

### Фактическая публикация

Релиз опубликован из merge commit
`fe9529419122948a3527c325bb5b0f1bc807d5c3` под тегом `v0.5.18`. Hosted package
run [35580270465](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35580270465)
прошёл для Linux и Windows; Windows portable/installer взяты из этого run,
Linux portable/`.deb` собраны из того же merged source tree после успешного
hosted Linux smoke.

Старый release job остановился на обязательной проверке отсутствующих
`CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID`. Worker был задеплоен локально
авторизованным Wrangler, версия
`b98aa8d7-a4a7-48bb-aac6-792533149fe3`; все шесть R2 объектов прочитаны обратно
через публичный Worker и совпали с подготовленными байтами. GitHub Release
[v0.5.18](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.18)
содержит тот же набор файлов. Полные размеры и SHA-256 находятся в
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

В историческом v0.5.16 release-job мог остановиться на отсутствующих
Cloudflare credentials до публикации; текущий tag-контракт выше fail-closed
проверяет Cloudflare и APT credentials до любых внешних mutations.

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
