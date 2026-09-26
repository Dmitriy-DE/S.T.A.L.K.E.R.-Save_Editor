# Архив состояния и истории изменений (до v0.7.0)

Этот документ содержит историю изменений и инженерный статус проекта до версии v0.7.0.
Текущее состояние проекта см. в [docs/STATUS.md](../STATUS.md).

---

## v0.6.0 — канонический редизайн, проверенный на реальных сейвах — 2026-09-24

Новый desktop/browser UI (библиотека, редактор в три колонки, история,
настройки, Steam Cloud, экраны проверки/результата) собран по каноническим
макетам в `tools/ui_review/references/`. Перед релизом редизайн прогнан на
реальных сейвах S.T.A.L.K.E.R. 2, Call of Pripyat, Clear Sky и Shadow of
Chornobyl; найденные дефекты исправлены до тега:

- **CI висел часами** на всех ОС: пустой журнал диагностики открывал
  блокирующий `QMessageBox`. У разработчика журнал был, поэтому локально всё
  проходило. Тесты теперь работают в одноразовом профиле (HOME/XDG/APPDATA),
  не читают реальные сейвы/настройки и не пишут бэкапы в данные пользователя;
  статические `QMessageBox` и `openUrl` заглушены, job падает через 30 минут.
- Библиотека и история падали на Windows с не-русской локалью: даты
  форматировались `strftime("Сегодня, %H:%M")`, а Windows кодирует формат
  локалью C runtime → `UnicodeEncodeError` для любого сейва/бэкапа за сегодня
  или вчера. Кириллица больше не проходит через `strftime`. Тестовый харнесс
  облака падал на Python 3.11/3.12 (`object.__setattr__` на виджете Shiboken);
  до Windows CI эти тесты раньше не доходили из-за зависания.
- Вкладки категорий инвентаря сравнивали английские ключи с русскими
  категориями парсера — на реальном сейве любая вкладка кроме «ВСЕ» была
  пустой (desktop и web). Теперь используется общая таксономия
  `editor.equipment`; патроны/гранаты — боеприпасы, бинокль X-Ray —
  устройство, у S2 артефакты/квестовые КПК и ключи/магазины распознаются по SID.
- Удалены захардкоженные под макет имена (`detector_advanced` показывался как
  «Велес», `helm_respirator` как «ПСЗ-7»). «Экипировка» показывает то, что
  сейв отмечает надетым (слоты X-Ray, equipped-строки S2), артефакты — с пояса.
- Вернулись функции, потерянные при редизайне: правка улучшений X-Ray,
  добавление предмета из каталога, «починить всё», «отменить все изменения».
  Вкладки панели предмета стали настоящими страницами; поля, которых нет в
  сейве, скрыты вместо «0 %»; предложены только размещения, которые принимает
  codec X-Ray.
- Шапка показывала литерал `v0.5.21`; версия читается из `VERSION` (desktop,
  updater, web). Окно перетаскивается через `startSystemMove` (Wayland),
  есть ручка изменения размера, стартовый размер берётся от экрана, узкие
  окна переходят в компактный режим без скрытых колонок.
- Подтверждение перед потерей черновика при открытии другого сейва, облака и
  закрытии окна. Служебные `CampaignsSave.sav`/`AnalyticsData.sav` S2 не
  попадают в библиотеку; русские плюралы, человеческие даты, деньги S2 в
  купонах, читаемые имена источников бэкапов.
- Настройки больше не рисуют неотключаемые «тумблеры» (один — для
  несуществующей функции); экран персонажа показывает распарсенную группировку
  игрока и не держит мёртвую панель «Параметры».
- Call of Pripyat получает русские имена одинаковых для серии ключей
  (артефакты, патроны, еда, устройства, группировки) из каталогов CS/SoC;
  оружие и костюмы не заимствуются — их названия в играх разные.
- Мёртвый код после редизайна удалён; ~30 МБ сгенерированных PNG ревью больше
  не хранятся в git, тесты ревью-инструмента рендерят метрики из текущего кода.

Локальный gate: `786 passed` (pytest в изолированном профиле), 14 Node tests,
Ruff, mypy, generated web/theme checks, `git diff --check`. Не проверено в этой
сессии: реальное перетаскивание окна на Wayland руками, live Steam
`WriteFile`/read-back и загрузка изменённых сейвов в игре.

Ревью ядра после мерджа редизайна (до тега):

- **Гейт возможностей на границе формата.** `prepare()` S2 передавал в писатель
  любой план, поэтому CLI мог записать в сейв S2 неподтверждённые стаки,
  перемещения, удаления и raw-патчи — матрицу проверял только UI. Теперь S2 и
  X-Ray `prepare()` отклоняют каждое поле без writable-возможности; raw/attach
  не пишутся никогда.
- **План «удалить + изменить».** Удаление предмета сбрасывало только черновик
  количества; состояние/размещение/апгрейды оставались, и писатель X-Ray падал
  на уже удалённом объекте. `EditPlan` отклоняет такой план, UI сбрасывает все
  черновики предмета и блокирует его до «ВЕРНУТЬ ПРЕДМЕТ».
- **Апдейтер** прерывает загрузку, превысившую размер из манифеста (раньше
  тело писалось целиком до проверки размера/SHA).
- Остальные пути записи прочитаны без замечаний: локальная замена (эксклюзивный
  бэкап, повторная SHA источника, атомарная замена, read-back), облачная
  транзакция (свежее чтение до `WriteFile`, после него — только uncertain),
  распаковка обновления (allowlist хостов и редиректов, защита от path
  traversal, откат при сбое).

**S2, сейвы стартовой версии.** Из 52 локальных слотов владельца открываются
34 — все 2026 года. 18 слотов декабря 2024 (4.6–5.1 МБ) содержат GUID поля
кошелька ровно один раз, но в старой раскладке без подтверждённого якоря.
Детектор теперь опознаёт эту раскладку (`legacy S2 layout`), а UI говорит
загрузить слот в игре и сохранить заново. Писать в старую раскладку не будем
без доказательства.

**Имена Call of Pripyat.** Причина английских имён — загрузчик каталога
предпочитал `text/eng`. Теперь rus → eng → любые; `tools/localize_cop_catalog.py`
перевыводит имена из оригинальной распакованной gamedata тем же парсером
(`inv_name` + русские таблицы). CoP: 0 → 215 русских имён предметов, 654
апгрейда вместо токенов `st_up_*`. Имена — игровые: `wpn_val` в оригинальной
CoP называется «СА «ЛАВИНА»», а «АС «Вал»» — переименование из патч-модов.

У S2 без Zone Kit/Workshop имена — это SID из сейва, иконки — глифы категорий.

## v0.5.21 — published root release; APT pending key recovery — 2026-09-22

Публичный root-релиз завершён из чистого `main` commit
`86cd76e3fb44c93249cb31f2da59ad204d4660e5` после PR
[#121](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/121),
[#122](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/122),
[#123](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/123) и
[#124](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/pull/124).
Финальный tagged workflow
[#35787422476](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35787422476)
прошёл source gate, Windows portable/installer smoke и Linux portable/`.deb`
smoke. Windows build корректно собран в CI, а Linux package собран на glibc
2.35 baseline.

База проверки: tagged source commit
`86cd76e3fb44c93249cb31f2da59ad204d4660e5`; опубликованные пакеты собраны из
этого CI source tree. Документационные изменения ниже не входят в байты
`v0.5.21` и публикуются отдельным docs-only merge.

- панель отношений/группировок больше не показывается для S.T.A.L.K.E.R. 2;
- CFG-каталог S2 принимает отдельный путь Zone Kit/Workshop, распознаёт
  вложенный `Stalker2/Mods/<name>/Content/...`, common JSON localization и
  loose PNG/JPG/WebP/BMP/DDS icon references; выбранный ресурс остаётся
  read-only presentation metadata;
- Cloud picker скрывает старые `-edited.sav`, upload повторно читает именно
  выбранный исходный remote path, делает backup/recovery и не ретраит
  неоднозначный `WriteFile`;
- изменённый S2 stream пересобирается bundled native Kraken encoder вместо
  15 MB stored-block fallback, с CRC/decompression/round-trip проверками.
- единая equipment-модель теперь различает weapon/armor/helmet/module/device/
  consumable/ammo/artifact/quest/other, хранит provenance и source observation;
  ПНВ и бинокль не получают выдуманную прочность;
- S2 Data-корпус отдельно показывает source-backed condition через один
  структурный codec для всех принятых actor-owned weapon rows с точным anchor
  (Kharod/Lavina/Skif — примеры текущего корпуса, не allow-list); direct
  modules и upgrade vectors остаются read-only, а наблюдаемые
  `NVG_NPC_Gen3`/бинокль — device без repair control;
- для известных save-local S2 IDs добавлены безопасные презентационные названия
  (Kharod, «Лавина», Сайга Д-12, ПНВ, бинокль). Official loose CFG/localization,
  Zone Kit и явно выбранный Workshop по-прежнему дают реальные names/icons;
  при отсутствии ресурса показывается category glyph, а не пустая ячейка;
- X-Ray matrix теперь отдельно описывает модули и устройства SoC/CS/CoP;
  Enhanced Editions остаются честно unsupported до реального sample;
- локальные diagnostics ограничены rotation/age/total-size, редактируют только
  redacted bundle, экспортируются и отправляются в отдельный R2 diagnostics
  prefix с rate-limit/lifecycle guard.

Локальный source gate после финальных исправлений: `669 passed`, 9 Node tests,
Ruff, mypy, generated web/theme checks и `git diff --check` проходят. Публичные
артефакты подготовлены из CI, а не из локального dirty checkout:

| Артефакт | Размер | SHA-256 |
|---|---:|---|
| Windows portable `.zip` | 62,624,891 | `38b46733441f35a0f2a97406aef9c1d2312fcf834811e23ed5ed30f45efe15cf` |
| Windows installer `.exe` | 38,427,714 | `528ca8285175edb43854fdd2271e4a6bc89f45cf865c86d5b5a43ae224704b1a` |
| Linux portable `.tar.gz` | 80,480,887 | `4e0a33adac7f9cd9d305aa18e789474f4023ac30a91a6a8c92b57b0307fc539d` |
| Debian `.deb` | 85,564,718 | `40ba725788a422b0579b945a6a89b49da6c2a440a94674d1dbec227ec42e9141` |

GitHub Release [v0.5.21](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.21),
R2 Worker [`latest.json`](https://save-editor-downloads.save-editor.workers.dev/latest.json)
и каждый публичный download URL прочитаны обратно; GitHub и R2 совпали с
локальными SHA/размерами побайтно. OTA manifest сообщает `0.5.21` и тот же
source commit.

Release job не получил `CLOUDFLARE_*` и `APT_SIGNING_*` secrets, поэтому Worker
был обновлён авторизованным Wrangler вручную, root-объекты R2 опубликованы и
проверены вручную, а GitHub Release создан из тех же байтов. APT не публиковался:
исходный private signing key отсутствует; генерация нового ключа запрещена,
чтобы не сломать доверие клиентов. Live Steam `WriteFile`/read-back и загрузка
изменённого слота игрой остаются отдельными внешними runtime-gates.

## v0.5.20 — native Steam Cloud writer with remote-only listings — 2026-09-21

Исправлен ложный read-only блок upload. Steam `GetFileCount()` перечисляет
только локально синхронизированные файлы и может вернуть `0`, когда сейвы уже
видны в Steam Cloud web/cache. Раньше transport смешивал источник списка с
возможностью записи, поэтому cache/web fallback отключал upload и показывал
`WriteFile не запускался`. Теперь после успешной native инициализации список
может оставаться web/cache-источником, а запись идёт через native
`RemoteStorage::FileWrite`; настоящий web/cache-only transport по-прежнему
остаётся read-only.

Локальное доказательство: `601 passed`, `make check`; read-only smoke текущей
Steam-сессии получил `52` cache-записи S.T.A.L.K.E.R. 2 и показал
`writable=True` с native writer. Реальный `WriteFile` в пользовательский слот,
его persisted/read-back и загрузка сейва в игре остаются отдельными внешними
runtime gates и в этой проверке намеренно не запускались.

Standalone package run
[35638429573](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35638429573)
прошёл source gate, Linux portable/`.deb` и Windows portable/installer smoke.
Его release job остановился до внешних мутаций на отсутствующих secrets
`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `APT_SIGNING_KEY` и
`APT_SIGNING_KEY_ID`. Поэтому шесть root-ассетов были вручную опубликованы
авторизованными `gh` и Wrangler из того же merge commit
`1adb396b8ddcc4ffb3c4f566c32560726ce5ea55`:
[GitHub Release v0.5.20](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.20)
и публичный [R2 Worker](https://save-editor-downloads.save-editor.workers.dev/latest.json).
GitHub download и R2 read-back совпали с локальными файлами побайтно; `latest.json`
публично сообщает `version: 0.5.20` и тот же `source_commit`. APT-репозиторий
не изменялся: без исходного приватного signing key его публикация запрещена.

SHA-256 бинарных ассетов v0.5.20: Windows portable
`f3d21583c8999a8d84283684a5ff45d20b105bc9bf538e59f6d22edee372d3ba`, Windows
installer `64e1ee9da8622449f42c41aaaadbccfd2722c04df07161c4eac1b5ef537109a5`,
Linux portable `82b7dfa49d00464a4bf3e5180a1fceafa457176e87d6850861b71ac15a03ede0`,
Debian `7c6c05f762f9adf2c2fa35f2b9b58c346b119e76eb6adca39b2d8d0a492e97bb`.

## v0.5.19 — one-click desktop save flow — 2026-09-21

Основной desktop flow упрощён до одной операции: открыть локальный сейв,
изменить данные и нажать **Сохранить**. Приложение задаёт одно подтверждение,
после чего само выполняет preview, fresh SHA/CRC-проверку, проверенный backup и
atomic replacement открытого слота. Ручные destination/preview/apply/replace
контролы убраны из обычной вкладки; журнал изменений и резервные копии остались
доступны как технические поверхности аудита и восстановления. Steam Cloud
сохраняет отдельное подтверждение upload и fail-closed границу.

Локальный gate: `575 passed`, `make check`. Hosted source matrix
[35587937545](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35587937545)
прошла на Ubuntu/Windows для Python 3.11/3.12. Hosted standalone package run
[35588193488](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35588193488)
прошёл Linux и Windows package/smoke jobs; его release job остановился
fail-closed на отсутствующих GitHub secrets `CLOUDFLARE_API_TOKEN` и
`CLOUDFLARE_ACCOUNT_ID`.

После успешных package jobs тот же набор байтов опубликован вручную
авторизованным Wrangler и `gh` из merge commit
`f44377d12da5d78c24c1afb3b5acf78e8b906a74`. Worker version
`52856335-1c63-450f-9183-50a1a7ee8e56`; все шесть R2 объектов прочитаны через
публичный Worker и совпали с локальными SHA-256. [GitHub Release v0.5.19](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.19)
содержит Windows installer/portable, Linux portable, `.deb`, `latest.json` и
`SHA256SUMS`.

После финального standalone run
[35623997966](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35623997966)
из commit `e11f469a8bc6df8b2980db765f635cb53fe4ac3c` эти шесть файлов вручную
заменены одновременно в R2 и GitHub Release авторизованными Wrangler/`gh`;
R2 read-back и GitHub download совпали побайтно. Тег `v0.5.19` не переписывался.
APT-индексы не трогались из-за отсутствия исходного приватного signing key.

Фактические assets после refresh: Windows portable — 62,315,347 bytes,
`77989c6696c220744ada8afb4c0d57a6ecf8f698c5bbab4c7fb5c1a13014b3f8`;
Windows installer — 38,264,578 bytes,
`66c9feef9c1e806b0a0e3145dd8fe8f678827fe884c5381054346f46c5cbfccf`;
Linux portable — 79,239,602 bytes,
`9e1633d771da6c724cdd55bb383264e589d2c68613b01385e2ae22674af1a157`;
Debian — 85,215,576 bytes,
`d2c29f987a6b96e0dbf605850a84db09e96a285fce0ee8ea2a270dbe10e2456b`.

## v0.5.18 — Cloud provenance, diagnostics and OTA correction

Steam Cloud cache rows now carry provenance and are read through the source that
found them. A metadata-only `remotecache.vdf` entry cannot fall through to the
native `FileRead` call that produced the false “файл отсутствует в облаке” error;
the UI labels local cache, metadata, web, helper and native sources separately.
Local cache bytes are accepted only when their size matches Steam metadata, with
web retry or an explicit read-only/unavailable error otherwise.

The desktop app configures a rotating `save-editor.log` (1 MiB plus three
backups) under its platform data directory. **Отправить логи** sends a bounded
redacted gzip to the existing download Worker; the Worker stores random
`diagnostics/` objects, does not serve them publicly, and removes objects older
than 30 days during later submissions. No save bytes are collected.

Linux package installation is now detected before the generic build manifest,
so `/usr/lib/stalker2-save-editor` selects the Debian artifact. Verified `.deb`
files use `pkexec apt-get` when available and otherwise `xdg-open`; Windows
installer and portable update paths remain separate. The application reports
that installation is pending instead of claiming that a package was already
updated.

Local implementation evidence is recorded in
[`evidence/CLOUD_DIAGNOSTICS_OTA_2026-09-21.md`](../evidence/CLOUD_DIAGNOSTICS_OTA_2026-09-21.md).
Hosted package smoke, Worker deployment, diagnostics intake policy, public
manifest read-back and the v0.5.18 release are complete. Live Steam Cloud
read/write, privileged package installation and in-game load/re-save remain
separate runtime gates.

The desktop save flow is now one action: after staging an edit, **Сохранить**
asks for one confirmation, then runs preview, fresh SHA/CRC verification,
verified backup and atomic replacement of the opened local slot internally.
Manual preview/output/apply controls are hidden from the normal workbench; the
change journal remains an audit surface and the backup screen remains a
recovery surface. Steam Cloud keeps its explicit upload confirmation and
fail-closed transaction boundary.

## v0.5.17 — hardening release — 2026-09-20

Cloud upload теперь включается только для native/helper transport, который явно
подтвердил write capability. Steam web/CDP и локальный cache остаются
read-only: список и скачивание доступны, кнопка upload выключена с конкретной
причиной. Отказ до вызова `WriteFile` имеет определённый no-write результат;
ошибка после начала записи остаётся `uncertain` и не запускает автоматический
повтор.

Updater проверяет каждый redirect до соединения с новым host. После успешной
замены portable tree ошибка удаления backup больше не откатывает рабочую новую
версию: старое дерево остаётся как восстанавливаемая копия. Release workflow
требует оба Cloudflare secret, один раз готовит stable directory, публикует и
читает его обратно через R2/Worker, затем передаёт те же шесть файлов (четыре
пакета, `latest.json`, `SHA256SUMS`) в GitHub Release.

Browser bootstrap параллельно начинает загрузку ooz, Pyodide, Python bundle и
bridge. File picker становится доступен после установки bridge; каталог
догружается отдельно, но анализ сейва ждёт его и показывает ошибку вместо
частично инициализированного редактора. Проверенный dead code удалён; публичные
`gog_roots`/`xbox_roots` сохранены как контракт M03.

Границы не расширены догадками: S2 weapon/helmet condition, произвольная выдача
и upgrades, Enhanced Edition parser, реальный Steam `WriteFile` и игровой
load/re-save остаются внешними evidence gates. Локальная/hosted/release
верификация фиксируется отдельно в
[`HARDENING_0.5.17_2026-09-20.md`](../evidence/HARDENING_0.5.17_2026-09-20.md).
Source gate релиза прошёл локально: Ruff, mypy для Linux и Windows target,
generated-file checks, `560 passed` и два Node bootstrap test. Clean-tree Linux
package build также прошёл: portable diagnostic загрузил bundled decoder,
native child завершил read-only list, а SHA-256 portable/`.deb` совпали.

Публичная публикация завершена из commit
`639557bc656e40681b63e4edf848c12fce7068e9`. Hosted source matrix
[35538975049](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35538975049)
прошла на Ubuntu 3.11/3.12 и Windows 3.11/3.12. Hosted standalone build
[35539090000](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35539090000)
прошёл на Linux и Windows, включая Windows portable, installer и smoke
установленного приложения.

Автоматический release job остановился на fail-closed проверке отсутствующих
`CLOUDFLARE_API_TOKEN` и `CLOUDFLARE_ACCOUNT_ID`; он не опубликовал неполный
релиз. После успешных package jobs тот же проверенный набор был опубликован
локальным авторизованным Wrangler/`gh`: Worker version
`e9b23133-910d-4d73-9ab7-8933cbac041a`, шесть R2 объектов и публичный
read-back совпали по размерам и SHA-256. [GitHub Release v0.5.17](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.17)
содержит четыре обязательных пакета, отдельный Windows installer,
`latest.json` и `SHA256SUMS`. Манифест содержит source commit
`639557bc656e40681b63e4edf848c12fce7068e9`.

Финальные hosted assets: Windows portable — 62,019,536 bytes,
`e62ac213394b817250ede47eec67ca48179189c612f1c7824778e57e1eb31e8b`;
Windows installer — 38,195,465 bytes,
`6554147ac2299d2a11edf6d3ac36d118bbe5d8b9015047a86faf46d17aada64b`;
Linux portable — 89,790,188 bytes,
`ea1547e591ff78eafc8629c00acaddcae489b7538ea89fdab116c25a5d4c8f4a`;
Debian — 93,125,120 bytes,
`863b7d0c3a96a3def35b41ef7fa2ff7b2a1f9831eedf6a518b7bf36b9378e987`.
Pages deployment `7e3cd3e8` отвечает через canonical URL HTTP 200 и содержит
раздельные ссылки Windows installer/portable и Linux packages.

## v0.5.16 — issues #95–#99 continuation — 2026-09-20

The shared bounded-mutation protocol now covers condition, confirmed X-Ray
upgrades, and confirmed X-Ray placement for controlled manual game-validation
runs. The S.T.A.L.K.E.R. 2 writer remains limited to the source-backed equipped
armor condition anchor; S2 weapon/helmet condition, upgrades, add-item and
unknown records stay read-only. This is implementation and round-trip evidence,
not a game load/re-save result.

Steam Cloud now uses one release-aware profile table for all seven official
Steam app IDs. S2 keeps `Data/*.sav`; original and Enhanced Edition cloud
roots follow their official `savedgames` directory and retain extensionless or
sidecar candidates for safe content detection. The Cloud tab carries the
selected release/app ID into native, helper, cache and CDP list paths and shows
which backend answered. Live Steam Cloud upload was not run in this pass.

Enhanced Edition descriptors and cloud paths are safe and separate, but no EE
parser is enabled: this host still has no accepted EE save fixture or complete
serialization evidence. EE bytes therefore fail closed instead of being sent
through an original X-Ray parser. The browser save action now performs its
existing preview/verification gate automatically before downloading a new copy.

Local verification: `make check`, full `make test` (`547 passed`), and `54
passed` in the Qt/web/cloud-focused run. Tagged commit
`c47e62d509467b9caaed092994edbae4e02352ae` passed hosted Linux and Windows
source/build/package smoke in [run 35514835825](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35514835825),
including Windows portable diagnostic and installer smoke.

The hosted release job initially stopped at Worker deploy because repository
secrets were empty. The same CI artifacts were then published through the
authorized local Wrangler session: Worker version
`b5ba5517-a3a8-45d0-bc9a-a8cace7e64ad`, five R2 objects, and byte-for-byte
public read-back. [GitHub Release v0.5.16](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.16)
contains Windows installer/portable, Linux portable, `.deb`, `latest.json` and
`SHA256SUMS`.

Pages was redeployed from the release tree as preview
[fdd869f5](https://fdd869f5.stalker-save-editor.pages.dev/) and the canonical
[stalker-save-editor.pages.dev](https://stalker-save-editor.pages.dev/) responds
HTTP 200 with separate Windows installer and portable links.

Release/R2 assets: Windows portable 62,013,435 bytes,
`15a0234fc806ade556a9d630261008bc06a6c0db29d07aad13c502560b2dadd7`;
Windows installer 38,192,590 bytes,
`a06068bec04895e2a6d5bf1f4c52257278080312e6dbf307054c0eb9f9261f06`;
Linux portable 89,804,743 bytes,
`0f278378b780f2f137513c11bcdf73f81f12a9298e9509a3d18b228bbdc492b0`;
Debian 93,129,042 bytes,
`cb492a4cb94f1848cc9de9de33780ce011f374a36b2857c48077a15eacc34937`.

No personal save, live user-save cloud write, or game load/re-save was
performed; those remain manual gates on a backup copy.

## v0.5.15 — отдельный Windows installer и portable — 2026-09-20

Windows теперь имеет две отдельные сборки: `SaveEditor-windows-x86_64-setup.exe`
для обычной установки с ярлыком и `SaveEditor-windows-x86_64.zip` для portable
запуска. Linux сохраняет portable tar.gz и отдельный `.deb`. GitHub Release и
Cloudflare R2 получают одинаковые итоговые байты; `latest.json` и `SHA256SUMS`
строятся из финальных файлов.

Локальные проверки: `537 passed`, `make check`. Hosted run
[35508107671](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35508107671)
подтвердил source tests, Linux/Windows native packaging, packaged diagnostics,
реальную компиляцию Inno Setup и установку Windows `.exe` в smoke-папку с
последующим запуском установленного diagnostic executable.

Релиз [v0.5.15](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.15)
собран из commit `7306dcbde417e9374038d9d9f47d198e4dfc2053` и содержит оба
Windows варианта, Linux tar.gz, Debian package, `latest.json` и `SHA256SUMS`.
Worker версии `6075860d-b502-4ebe-b987-410a85bc51a8` задеплоен; пять стабильных
R2 object-ов загружены и прочитаны обратно через public Worker.

Live `UpdateClient` подтвердил на обеих ОС и для Windows installer: с версии
`0.5.14` результат `available 0.5.15`, с `0.5.15` — `current`, с выбором
правильного файла (`.zip`, `.exe`, `.tar.gz`, `.deb`). Pages preview revision
[db10e42b](https://db10e42b.stalker-save-editor.pages.dev/) и canonical URL
отвечают HTTP 200; страница содержит отдельные ссылки Windows installer и
Windows portable.

Автоматический release-job дошёл до сборки и упал только на deploy Worker из-за
отсутствующих repository secrets `CLOUDFLARE_API_TOKEN` и
`CLOUDFLARE_ACCOUNT_ID`; R2, Worker и GitHub Release завершены локальным
авторизованным Wrangler/`gh` без помещения OAuth-токена в GitHub.

## 2026-09-20 — S2 Zone Kit / Steam Workshop catalog discovery

S2 catalog теперь обнаруживает official install roots, явные Zone Kit roots и
Steam Workshop `content/1643320` roots. Loose Workshop layout читается только
через opt-in overlay provider; реальные CFG display names, upgrade names и
icon paths передаются в общий catalog/icon resolver. `.pak` и Blueprint не
распаковываются, а S2 add/upgrade/repair writer и SID/type-key mapping от этой
метаинформации не включаются. Подробности: [S2 Zone Kit / Steam Workshop
evidence](../evidence/S2_ZONEKIT_WORKSHOP_2026-09-20.md).

## 2026-09-20 — merged main, local cleanup и Pages continuation

Merged `main` — `0f9d207`. После merge подтверждены `496 passed`, `make check`,
Linux packaged diagnostic и SHA256 read-back двух локальных v0.5.8 artifacts.
Pages preview revision `d555bfc9` отвечает HTTP 200; canonical Pages URL также
отвечает HTTP 200. Старые локальные ветки/worktrees и caches удалены, личные
fixtures вынесены из checkout во внешний пользовательский архив.

Это не подтверждение Steam `WriteFile` и не доказательство game load/re-save:
такие gates остаются ручными и выполняются только на резервной копии конкретного
слота.

## 2026-09-19 — S2 equipment condition writer (experimental)

Для подтверждённой S2 actor-owned брони добавлен experimental condition
reader/writer: equipped records с exact nested shape показываются в inventory,
condition можно застейджить и проверить после container rebuild. UI больше не
рисует неизвестную прочность как ложные `0%`, а показывает `—`. Это не доказано
игровым load/re-save: [S2 equipment writer evidence](../evidence/S2_EQUIPMENT_WRITER_2026-09-19.md)
содержит controlled-pair протокол.

Weapon condition, upgrades и выдача предметов из S2 каталога остаются
read-only: для них нет подтверждённого differential serializer/allocator.

## 2026-09-19 — v0.5.8: Proton Data discovery и Cloud transaction UX

Выпущенный проход добавляет legacy Proton-путь S.T.A.L.K.E.R. 2 без manifest,
отдельный `SaveGames/Data` search root и прямую проверку на текущем хосте:
автопоиск нашёл 53 S2 `.sav`, включая `217BB29D4FA4C87BD9F734AE755338CB.sav`.
Пути оригинальной трилогии на выбранном Steam root совпали с
`STALKER Shadow of Chernobyl/_appdata_/savedgames`, `STALKER Clear Sky/_appdata_/savedgames`
и `Stalker Call of Pripyat/_appdata_/savedgames`.

Добавлен refresh для истёкших CDP download URL, синхронизация game picker с
content-detected snapshot и контрастные discovery labels. Cloud snapshot в
рабочей области теперь явно показывает `Сохранить и загрузить в облако`.
Локальные gates: `442 passed`, `make check`. Тег `v0.5.8` указывает на
`103ec666d091754024c2073d2e435f586cb4e688`; source CI
[35446190978](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35446190978)
прошёл четырьмя matrix jobs, standalone build
[35446471756](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35446471756)
прошёл Linux/Windows packaged diagnostics, а
[GitHub Release v0.5.8](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.8)
опубликован с portable Linux, Debian, Windows и SHA256SUMS.

Stable-файлы в Cloudflare R2 обновлены и прочитаны обратно через Worker:
публичные SHA256 совпали с CI (`12dc2d26…aaa8e7` Linux,
`a125a55c…c6c82` Debian, `aec3e7ed…2ea40` Windows). Pages revision
`72b9aa0d` отвечает HTTP 200 и содержит три stable download link.
Live read-only smoke получил 50 remote S2 slots и скачал один слот через Steam
web. Live `WriteFile`, игровой load/re-save и системная установка `.deb`
остаются отдельными внешними gates.

## 2026-09-19 — v0.5.7: Steam Cloud web fallback и синхронизация игры в редакторе

Исправлен конкретный UI-баг из ручного импорта: после открытия S.T.A.L.K.E.R.
2 быстрый game/save picker больше не оставляет первым семейством Shadow of
Chornobyl. Он синхронизируется с `format_id` фактически распознанного snapshot,
включая cloud snapshot.

Cloud transport теперь не считает пустой `RemoteStorage::GetFiles` доказательством
пустого облака. После bounded native/helper list он читает локальный Steam
`remotecache.vdf`; если пользователь одним действием включил CEF debugging,
тот же transport получает строки и короткоживущие download URL из авторизованной
Steam Cloud web-страницы через localhost CDP. Скачивание идёт через этот URL,
а `WriteFile`, `SyncCloudFiles`, persisted и read-back SHA остаются на native
Steam API. Вкладка показывает честное состояние `найдено в Steam cache`, если
debug-порт ещё не включён, и содержит кнопку, которая явно перезапускает Steam
с `-cef-enable-debugging`.

Live read-only smoke на текущей Linux Steam-сессии: новый helper перезапустил
Steam с debug-портом, получил 50 `Data/*.sav` через web fallback и скачал
`217BB29D4FA4C87BD9F734AE755338CB.sav` размером 6,722,835 bytes. `WriteFile`
не запускался; cloud upload и игровая загрузка/re-save по-прежнему требуют
отдельного осознанного ручного прогона.

## 2026-09-19 — v0.5.6 опубликован: bounded native cloud transport

Пользовательский `v0.5.4` зависал на вкладке Steam Cloud после загрузки
`steamclient.so`: старый UI worker вызывал `ctypes`-native backend напрямую, а
30-секундный watchdog только менял текст и не мог прервать зависший native
вызов. Добавлен `SteamNativeSubprocessWorker`: каждая native операция живёт в
отдельном дочернем процессе с hard timeout; только ошибка первичного `list`
может выбрать bounded helper fallback, повторные cloud-операции backend не
переключают.

В corrective pass добавлены отдельный console `SaveEditor-native` для frozen
Windows/Linux child protocol, реальный killable `Popen` handle, cancel перед
закрытием Qt и hard deadline для `wait_persisted`; CI packaged smoke запускает
этот child на обеих ОС. Локальные проверки: `435 passed`, `make check`, source
Qt smoke и standalone child smoke прошли; live read/write пользовательского
сейва, игровая загрузка и повторное сохранение в игре остаются отдельными
внешними ограничениями. Тег `v0.5.6` указывает на
`797884d9dcd372bc45e5b9a78ddd6f47590cc124`; tag-build
[35406902752](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35406902752)
прошёл на Linux и Windows, а GitHub Release опубликован
[здесь](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.6).
Стабильные Linux/Windows/Debian ссылки страницы загрузок отвечают `200 OK` и
ведут на артефакты этого же CI build. Реальный пользовательский Steam Cloud
read/write, game load/re-save и установка системного `.deb` с правами root не
входили в удалённые gates.

## 2026-09-18 — v0.5.1: UX по фидбеку

- **Облако само подключается в фоне.** Поле «Steam helper» убрано целиком
  (это был footgun — туда попадал мусор вроде пути к `claude`). Вкладка Steam
  Cloud коннектится сама при открытии; ручной шаг и путь к helper'у больше не
  показываются. SC-2 позднее удалил внешний worker transport; подключение идёт
  через native Steam worker.
- **Веб-ссылки на скачивание починены.** Были захардкожены на `v0.4.0` → 404.
  Теперь ведут на `releases/latest` со стабильными именами; добавлена кнопка
  `.deb`-установщика и «Все сборки».
- **Linux-установщик приложен.** `.deb` **уже собирался** сборкой, но не
  прикладывался к релизу — теперь прикладывается (ставится двойным кликом /
  `apt install ./...deb`, появляется в меню приложений).
- **Настройки: автопоиск сразу по всем играм.** Добавлена сводка «нашёл (все
  игры)» — выбирать игру для просмотра найденного не нужно.

Исторический долг о многошаговом сохранении закрыт последующим UX-проходом:
preview, SHA/CRC, backup и запись теперь запускаются одной кнопкой после
одного подтверждения, без удаления fail-closed проверок.


## 2026-09-18 — v0.5.0: встроенное облако, автопоиск-подсказки, вёрстка

- **Steam Cloud внутри проекта.** Добавлен `editor/steam_native.py` — native
  worker на `ctypes` поверх `libsteam_api` (ISteamRemoteStorage), запускаемый
  через killable child transport: init/list/read/write/sync.
  `editor/steam_backend.py` выбирает bounded native transport, а при ошибке
  первичного списка может откатиться на helper. Сторонний Rust-проект больше
  не обязателен. Live `init + connect + list` подтверждён только локальными
  smoke-прогонами с пустым списком; реальный read/write остаётся на
  пользовательской проверке.
- **Краш `libfuse.so.2` устранён.** Helper-fallback распаковывает AppImage
  через `--appimage-extract` (без FUSE) и запускает внутренний ELF; проверено
  локально (`Ping/Pong`).
- **Автопоиск-подсказки во всей апке.** Под полями Steam root / папка игры /
  папка сейвов показывается реально найденный путь (или «ничего не найдено»)
  для каждой игры; Clear Sky/SoC/CoP находятся, Steam root тоже.
- **«Неизвестно» → «—» с тултипом.** Инвентарные поля, которых формат не
  хранит, показываются как «—» с объяснением, а не пугающим «неизвестно».
- **Вёрстка.** Стековые вкладки обёрнуты в один предсказуемый скролл; убраны
  наезды/обрезка; карточки локация/время для S2 показывают «—» с GVAS-тултипом
  (схема UE5 GVAS по-прежнему не разбирается — это вне скоупа релиза).

## 2026-09-18 — опубликован v0.4.3

Тег `v0.4.2` оставлен неизменяемым, но GitHub Release для него не создавался:
Linux standalone job прошёл, а Windows source-test job завершился с
`0xC0000409` при завершении Qt worker. В `v0.4.3` добавлено ожидание
save-discovery worker при закрытии окна и регрессионный тест на этот сценарий;
standalone workflow #35350988272 прошёл на Linux и Windows, assets опубликованы
в [GitHub Release v0.4.3](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.4.3).

На ветке release-кандидата исправлены проблемы, видимые в старом бинарнике
`v0.4.0`:

- карточка денег больше не затирает найденное значение в `—`; S2 money можно
  застейджить и подготовить к preview как отдельное экспериментальное поле;
  stacks, неизвестные handles и остальные неподтверждённые мутации остаются
  read-only;
- S2 embedded save-local name table подключена к inventory presentation;
  неизвестное имя по-прежнему показывается честно вместе с type-key/handle;
- inventory получил приоритет широкой колонке имени, минимумы для технических
  колонок, горизонтальный скролл и двухстрочные action-группы вместо сжатой
  строки из четырёх кнопок;
- отсутствующие в текущем S2 parser location/time показываются как `не
  разобрано`, а не как пустая/выдуманная метрика;
- На момент этого исторического снимка SteamCloudFileManager использовался как
  внешний JSON worker adapter.
  Discovery находит распакованный Linux asset с соседней библиотекой,
  `Ping`/`Connect` прошли локально; `GetFiles` вернул 0, upload не выполнялся.

Парсер S2 money и его decompression/CRC/SHA/round-trip guards не являются
доказательством принятия изменённого файла игрой. Для этого нужен отдельный
load/re-save evidence row на конкретной версии S.T.A.L.K.E.R. 2.

## 2026-09-18 — Zone launcher и вход в Steam Cloud

Desktop теперь стартует с единой read-only библиотекой: все четыре семейства
официальных игр и найденные локальные `.sav`/`.scop` отображаются сразу,
выбор игры фильтрует список, а неизвестные файлы остаются видимыми с честным
статусом. `ИМПОРТ СЕЙВА…` открывает внешний файл через content-only detector и
не требует установленной игры.

На стартовом экране добавлена явная кнопка `STEAM CLOUD`, которая переводит в
существующий Qt Cloud flow без предварительного локального сейва: helper
подключается, перечисляет удалённые `S.T.A.L.K.E.R. 2` `Data/*.sav`, выбранный
слот скачивается и анализируется, а подготовленный preview можно отправить
обратно через fail-closed transaction с backup, fresh SHA, persisted-проверкой
и read-back SHA. Транспорт по-прежнему S.T.A.L.K.E.R. 2-only; оригинальная
трилогия/Enhanced Edition и live runtime без установленной игры требуют
отдельного evidence и здесь не объявляются подтверждёнными.

Локальная проверка этого прохода: `PYTHON=.venv/bin/python make check` — exit 0,
`PYTHON=.venv/bin/python make test` — exit 0 (`411 passed`); `make package-plan`
и Linux packaging выполняются отдельно на текущем host.

## Актуальный official-release pass

После merge PR #53 текущая база `main` расширяет старый S2-only редактор одним
shared registry для официальных PC-профилей. Ветка M10 добавляет протокол
игровой проверки. Владелец подтвердил загрузку и сохранение подготовленных
сейвов в локальных оригинальных SoC/CS/CoP, поэтому их mutation capabilities
открыты; независимый SHA parser read-back второго сохранения не собирался:

<!-- HISTORICAL CAPABILITIES TABLE -->
| Release | edit_money | edit_stacks | move_items | add_items | remove_items | edit_durability | edit_upgrades | edit_relations | edit_player_faction | edit_placement | equipment_durability | equipment_upgrades | equipment_placement | equipment_add | equipment_remove |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S.T.A.L.K.E.R. 2: Heart of Chornobyl | experimental | experimental | unsupported | unsupported | unsupported | experimental | unsupported | unsupported | unsupported | unsupported | experimental | research | unsupported | unsupported | unsupported |
| S.T.A.L.K.E.R.: Shadow of Chernobyl | verified | verified | unsupported | verified | verified | experimental | unsupported | experimental | experimental | experimental | experimental | unsupported | experimental | experimental | experimental |
| S.T.A.L.K.E.R.: Clear Sky | verified | verified | unsupported | verified | verified | experimental | experimental | experimental | experimental | experimental | experimental | experimental | experimental | experimental | experimental |
| S.T.A.L.K.E.R.: Call of Pripyat | verified | verified | unsupported | verified | verified | experimental | experimental | experimental | experimental | experimental | experimental | experimental | experimental | experimental | experimental |
| S.T.A.L.K.E.R.: Shadow of Chornobyl — Enhanced Edition | experimental | experimental | unsupported | experimental | experimental | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| S.T.A.L.K.E.R.: Clear Sky — Enhanced Edition | experimental | experimental | unsupported | experimental | experimental | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
| S.T.A.L.K.E.R.: Call of Pripyat — Enhanced Edition | experimental | experimental | unsupported | experimental | experimental | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported | unsupported |
<!-- END HISTORICAL CAPABILITIES TABLE -->

Матрица показывает значения maturity из реестра формата и реестра equipment
без преобразования в L1–L5. Колонки `edit_*` берутся из `FormatCapabilities`,
`equipment_*` — из реестра официального релиза; поэтому одноимённые add/remove
оставлены отдельными колонками.

Desktop использует release-specific auto/manual save discovery; browser остаётся
local-file-only и content-detects файл тем же ядром. Capability flags теперь
управляют Qt/web controls, а M10 gate не позволяет синтетическому round-trip
выглядеть как доказательство загрузки в игре. Community mods намеренно вне
scope. X-Ray evidence:
[container](../evidence/XRAY_CONTAINER.md), [inventory](../evidence/XRAY_INVENTORY_2026-09-15.md),
[catalog](../evidence/XRAY_CATALOG_2026-09-15.md), [EE boundary](../evidence/EE_FORMATS_2026-09-15.md).

Локальный Linux gate текущего прохода: `PYTHON=.venv/bin/python make check` exit 0,
`PYTHON=.venv/bin/python make test` exit 0 (`283 passed`); ruff,
mypy, generated web bundle/theme и `node --check web/app.js` проходят. Linux
`tar.gz`/`.deb` и packaged diagnostic также собраны и проверены; Cloudflare
Pages revision `4d833b6f` прочитан обратно с HTTP 200 после обновления каталога и
поиска Enhanced-путей.
Точные хэши и URL записаны в
[release evidence](../evidence/RELEASE_2026-09-15.md). Это не заменяет Windows
runtime, живой game load/re-save, Steam/GFN или GitHub Pages.

## Подтверждённая база

Исходники v0.3.0 EXPERIMENTAL импортированы без изменения runtime. Linux self-test и синтаксис проверяются отдельно в [evidence](../evidence/BASELINE_2026-09-13.md). Денежные значения контрольных файлов: 48645, 58870, 56995; ранее изменённый D639: 900000. Это проверка распаковки/структур, не запуск игры.

В продукте один Qt-интерфейс и CLI поверх общего UI-free `EditorService`; Tkinter-интерфейс удалён после достижения Qt parity. Qt shell принят через [PR #39](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/39), inventory search/filter и staged money/stack forms — через [PR #40](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/40). U07 принят через [PR #47](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/47) (merge `658fe77`): поверх shell добавлены тёмная Zone-тема, structured metadata/CRC badges, sidebar и snapshot-backed summary cards; новые runtime-зависимости не добавляются. U04 принят через [PR #41](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/41): immutable preview и local apply используют тот же service/storage, bytes до preview не меняются. U05 принят через [PR #42](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/42): backup/hash browser и restore в новую локальную копию. U06 принят через [PR #43](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/43): Qt Cloud tab с явным connect/list/analyze и verified/uncertain upload. Подтверждённого Windows-дистрибутива пока нет; B01 добавляет builder для Windows zip, Linux tar.gz и Debian package. S06 добавляет локально проверенную cloud transaction state machine, но end-to-end Steam/GFN при импорте не выполнялся. P03 добавляет обязательную GitHub Actions matrix для Linux/Windows и Python 3.11/3.12; код слит через [PR #37](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/37), но пять запусков завершились `startup_failure` до создания jobs, поэтому runner evidence ещё ожидается. Baseline с исходниками: `2291832`.

## Найденные при аудите исходников риски и их покрытие

Таблица ниже — исходные находки чтения кода и карточка, которая их закрыла.
Все перечисленные карточки (S02–S06) приняты; строки остаются, потому что они
фиксируют, *почему* существуют соответствующие проверки, и их нельзя снимать
без нового evidence. Приёмочные матрицы: [`BETA_ACCEPTANCE`](../evidence/BETA_ACCEPTANCE.md)
и [UI design evidence](../evidence/UI_DESIGN_2026-09-13.md).

История приёмки карточек (какой PR что принял) вынесена в
[журнал приёмки](../history/ACCEPTANCE_LOG.md); актуальные статусы очереди —
в [tasks.json](../tasks/tasks.json) и сгенерированной из него
[таблице](../tasks/INDEX.md). Здесь остаётся только текущее состояние.

Привязки относятся к импортированному baseline. Это конкретные ограничения, не исчерпывающий аудит безопасности.

| ID | Сценарий и исходник | Что сделать |
|---|---|---|
| S02 | (удалённый app.py):480 превращает relative raw-offset в абсолютный при staging; save_format.py:742 применяет raw после attach/detach, меняющих длину массивов в :546. Адрес после массива может указывать уже на другие байты. | Запретить совмещение raw с изменением длины до доказанной адресации; привязать план к исходному SHA. |
| S02 | (удалённый app.py):143 отключает лишь четыре кнопки, а :557 читает staged-словари в фоне. Пользователь может менять правки после подтверждения. | Неизменяемый снимок правок до запуска worker. |
| S03 | cli.py:14–17 пишет прямо в output, допускает `-o` равный исходнику и перезапись существующей копии без backup. | Общий путь backup/atomic export для GUI/CLI, запрет same-path по умолчанию. |
| S03 | (удалённый app.py):523 использует timestamp до секунды; :572–573 пишет backup/output через write_bytes. Повторное имя может совпасть, прерванная запись оставляет частичный output. | UUID/exclusive backup, временный файл рядом с output, fsync/replace, fresh SHA локального источника. |
| S04 | save_format.py:353 пропускает неоднозначно распознанные handles; :361 разрешает все неизвестные kind кроме 0/1/2 при count>1. Неполный разбор визуально выглядит полным. | Отчёт coverage, неизвестные записи read-only, явные eligibility-правила. |
| S05 | steam_cloud.py:127 берёт Lock → _ensure():93 → start():87 → request() снова берёт тот же Lock при рестарте. Таймаут :113 оставляет читателя, который может забрать следующий ответ. | Управляемый lifecycle, один reader, уничтожение сессии после timeout; не ограничиваться заменой Lock на RLock. |
| S06 | `editor/transactions.py` теперь выполняет WriteFile/sync/persist/read через helper; `is_persisted` остаётся client-side flag и не доказывает серверный snapshot. | Реальный tagged helper/Steam run и game/GFN reload; в коде различать verified и uncertain. |

## Чего не хватает редактору

| Область | Сейчас | Задачи |
|---|---|---|
| Надёжность | Общий parser gate покрывает S.T.A.L.K.E.R. 2 и подтверждённые оригинальные X-Ray containers; полный release gate всё ещё требует Windows/runtime evidence | B02 |
| Linux + Windows | Decoder, пути, launcher и helper на обеих ОС; CI зелёная на обеих; Windows `.exe` собран и его diagnostic пройден на runner. Не проверен запуск окна на живом Windows-десктопе | B02 |
| Удобный UI | Qt и CLI используют общий service; Zone shell, metadata badges, summary cards, inventory search/filter, отдельный Equipment Editor с category/location filters и staged bulk repair, preview/apply, backup browser/restore и Cloud tab работают локально. U02–U07 приняты; открыт только native DPI/Steam smoke | B02 |
| Восстановление | U05 показывает journal/hash status и восстанавливает verified backup в новую копию; in-place replacement и cloud restore не реализованы | новая карточка (не заведена) |
| Названия и каталог | Оригинальные metadata-каталоги загружаются desktop/web; S2 embedded save-local name table разрешает текущие inventory keys, loose official CFG catalog читается read-only; переносимый prototype SID/локализация не доказаны | R01–R02, M21, M25 |
| Прочность | Experimental condition read/write добавлен для подтверждённых X-Ray weapon/outfit anchors и наблюдаемых S2 armor/weapon anchors; game load/re-save не выполнены | R03–R04, M12, S2 evidence |
| Новые предметы/clone | Для оригинальной трилогии работают catalog key + same-family registry template; S2 и неизвестные families запрещены | R05–R07 |
| Позиция предмета | Experimental `SInvItemPlace` read/write для actor-owned original SoC/CS/CoP; неизвестный anchor read-only, game load/re-save не выполнен | M20 |
| Настоящее удаление | X-Ray deep removal и Qt/web staging блокируют известные direct dependents, explicit equipped и unresolved targets; полный reference graph и game load/re-save не доказаны | M23–M24, R08 |
| Attachments/upgrades | `m_upgrades` подтверждён структурно для CS/CoP и доступен experimental; S2 direct modules и upgrade vectors показываются read-only, controlled attach/detach и game read-back отсутствуют; SoC/S2/Enhanced mutations остаются read-only | M17, R09–R10 |
| Размер output | X-Ray edit использует безопасный literal-only LZO writer; output может быть больше исходного | R11 |

Count=1 остаётся read-only в текущем stack editor. Нельзя просто разрешить все count=1: оружие/броня/квестовые объекты требуют отдельных правил и evidence. Полная поддержка других кампаний/версий игры также не доказана: MONEY_ANCHOR привязан к изученным сейвам.

Ранний файл 5967 читает 22645, скриншот показывает 30145. Причина не установлена; эти данные не составляют достоверную пару. Synthetic fixtures проверяют код, а не универсальность формата.

## Веб-версия

`web/` запускает то же multi-format ядро в браузере через Pyodide: `ooz-wasm`
для S.T.A.L.K.E.R. 2 и portable Python LZO для оригинальной трилогии. Веб
принимает файл локально, распознаёт только зарегистрированный формат и
отказывает на неизвестном; до M10 game load/re-save mutation controls остаются
read-only, хотя локальный writer и catalog round-trip продолжают проверяться
отдельно. Сверка S2
остаётся в [evidence](../evidence/WEB_EDITION_2026-09-14.md), X-Ray bridge
покрыт `tests/test_web_bridge.py`.
Steam Cloud в вебе невозможен по устройству Steam, а не по нашей лени:
[разбор вариантов](../evidence/STEAM_CLOUD_OPTIONS.md). Сайт опубликован: <https://stalker-save-editor.pages.dev>,
обновление — `make web-deploy` (Cloudflare Pages). Проверено
живьём: страница, стили, ядро, мост и metadata catalog отдаются с HTTP 200.

## M01 — реестр форматов — 2026-09-15

На ветке `codex/m01-format-registry` реализован статический реестр форматов
([PR #48](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/48),
commit `559bb1a`). В нём зарегистрирован только `stalker2`; адаптер делегирует
существующим `save_format.inspect_save` и `editor.prepare.prepare_edit`.
`EditorService` выбирает формат по содержимому, а local/Cloud snapshots
передают ID и title формата. `make check` и `make test` прошли локально на
Linux (`165 passed`). M02 и X-Ray форматы ещё не реализованы; Windows,
игровая загрузка и shared/production deployment этим результатом не доказаны.

## M02 — content-only detection — 2026-09-15

На ветке `codex/m02-format-detection` реализован общий отказ для неизвестного
формата ([PR #49](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/49),
commit `2e12375`). Core-сообщение включает имя файла, размер, причины отказа и
список поддержанных форматов и передаётся без повторной диагностики в CLI, Qt
и web bridge. Покрыты empty, truncated, мусорный бинарник, ELF-like чужой
бинарник и текстовый `.sav`; исходные байты не меняются. Полный Linux gate:
`make check` exit 0, `make test` exit 0 (`173 passed`). Реальные X-Ray сейвы,
Windows и игровая загрузка этим результатом не подтверждены.

## M03 — исследование и discovery путей — 2026-09-15

На ветке `codex/m03-save-locations` реализованы read-only поисковые функции в
`editor/platforms.py` ([PR #50](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/50),
commit `23a02a3`). `steam_roots` учитывает Windows registry/fallback и обычный,
legacy и Flatpak Linux; `steam_libraries` сам разбирает KeyValues
`libraryfolders.vdf`, пропуская битый root с warning; `installed_games`
проверяет appmanifest и каталог. `save_directories` включает четыре семейства,
S2 Steam/EOS/GOG/Microsoft Store, original `_appdata_`, Enhanced/Legends,
локализованные Documents, Proton prefix и `fsgame*.ltx` override.

Источниковые пути и пробелы evidence записаны в
[`SAVE_LOCATIONS.md`](../evidence/SAVE_LOCATIONS.md). Synthetic tree покрывает
alternate library, malformed VDF, localized Documents, Proton, Microsoft Store
profile и отсутствие записи. `PYTHON=.venv/bin/python make check` — exit 0;
`PYTHON=.venv/bin/python make test` — exit 0 (`183 passed`). Реальные установки,
Windows/GOG/Proton runtime и игровая загрузка не проверялись; отдельная GOG
path row для Clear Sky/Call of Prypiat Enhanced upstream-источниками не дана и
не объявлена подтверждённой.

## M04 — выбор слота из найденной папки — 2026-09-15

На ветке `codex/m04-save-slots` добавлена асинхронная read-only вкладка
«Найденные сейвы» ([PR #51](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/51),
commit `dc094b4`). Она использует кандидатные пути M03, перечисляет `.sav`,
сортирует их по времени изменения от новых к старым и определяет формат только
через общий content detector. Неизвестные файлы остаются видимыми с честной
пометкой; явное открытие использует существующий путь `MainWindow` и общий
`FormatDetectionError`. Пустой список показывает все проверенные пути, ручной
выбор файла сохранён, автоматического открытия и записи в игровые каталоги нет.
`make check` и `make test` прошли локально на Linux (`187 passed`). Реальные
X-Ray сейвы, Windows/Proton runtime и игровая загрузка этим результатом не
подтверждены.

## M05 — ручные пути и их запоминание — 2026-09-15

На ветке `codex/m05-manual-paths` добавлены versioned локальные настройки
([PR #52](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/52),
commit `851a30c`). JSON хранится в `user_data_dir()/settings.json`, пишется
атомарно и не попадает в репозиторий. Qt-вкладка позволяет задать корень Steam,
папку игры и папку сохранений по каждой игре. Действующий ручной путь имеет
приоритет над автоматическим поиском; исчезнувший путь показывает сообщение и
возвращает auto-search, а битый/чужой JSON заменяется в памяти пустыми
настройками без падения. `make check` и `make test` прошли локально на Linux
(`197 passed`). Реальные Windows/GOG/Proton установки и игровой runtime этим
результатом не подтверждены.

## M06–M09 — оригинальная X-Ray трилогия — 2026-09-15

В [XRAY_CONTAINER](../evidence/XRAY_CONTAINER.md) зафиксированы raw LZO1X,
внешний `magic/version/unpacked_len`, chunks и границы принятого корпуса.
Общий `editor/xray_save.py` добавляет SoC/CS/CoP через таблицу specs:

- SoC: outer 3, actor spawn 118, 4/4 локальных файлов;
- CS: outer 5, actor spawn 124 на локальном корпусе, 56/56 файлов;
- CoP: outer 6, actor spawn 128, 168/168 `.scop` файлов.

Qt, CLI и web используют один detector/reader. Автопоиск принимает `.sav`,
`.scop` и `.scs`-кандидаты, ручной picker и browser не ограничены расширением;
неизвестный формат получает явный отказ. На desktop поиск кеширует неизменившийся
size/mtime результат, а полный inspect всегда перечитывает bytes и SHA.

Локально реализованы и проверяются actor money и ammo stack count (STATE +
UPDATE), immutable `EditPlan`, source SHA, backup/atomic export и повторный
parse. Object windows и length-changing registry framing индексируются строго.
Для оригинальной трилогии catalog-backed writer добавляет предметы из
официального metadata-каталога через same-family registry template и удаляет
actor-owned record как deep operation; SoC/CS/CoP representative in-memory
прогон покрыл десять serializer families в каждом релизе. Эти локальные
До M10 эти базовые результаты не открывали UI/web mutation; Move, equipment, attachments
и reference-safe deletion остаются read-only. M12–M20 вынесли прочность,
отношения, player community, in-place replacement, X-Ray upgrades и placement
в отдельные stacked review-карточки; M17 (PR #65) и M20 (PR #68) структурно проверены,
но controlled game load/re-save для новых полей ещё не выполнялся.
Enhanced Editions также не объявлены поддержанными: evidence записан отдельно
в `EE_FORMATS_2026-09-15.md`.

Локальный корпус подтверждает чтение и no-op SHA-preserving round-trip; game
load/re-save, Windows runtime и Enhanced остаются внешними gates. Реализация и
регрессии находятся в текущем проходе ветки `codex/m06-xray-container`, а
исторические PR #53–#56 остаются открытыми документными карточками до
переноса соответствующих коммитов.

## Текущий проход B02

U07 оформил внедрение приложенного Stitch visual reference и принят merge
`658fe77` через PR #47. В runtime
перенесены только palette/layout hierarchy и bindings к реальному snapshot;
статические demo-значения и нерелевантный Figma Make music-проект исключены.
Два новых regression-теста и полный Qt suite проходят локально; provenance и
граница импорта записаны в [UI design evidence](../evidence/UI_DESIGN_2026-09-13.md).

B01 добавляет воспроизводимый PyInstaller onedir builder. Целевые результаты:
Linux x86_64 portable `tar.gz` и Debian/Ubuntu `.deb`, Windows x64 `zip` с
`SaveEditor.exe`; runtime Python, Qt и native decoder должны лежать внутри
bundle. Исходный core остаётся stdlib-only, `pytest` не попадает в runtime.

В текущем M18-проходе Support project добавлен как локальный Qt `QDialog` и
web modal с clipboard-only Copy/Copied feedback. Платёжные APIs, backend,
tracking, QR и startup/recurring popups не добавлялись; визуальная адаптация
X-Ray reference записана в [UI support evidence](../evidence/UI_SUPPORT_2026-09-16.md).

В M19 к Qt-инвентарю подключены release-scoped X-Ray icon coordinates и
официальный `ui_icon_equipment.dds` resolver: atlas читается только из выбранной
официальной установки и кэшируется в памяти. Web остаётся local-file-only, не
получает игровые ассеты и показывает доступный категорийный glyph; известные
координаты official atlas остаются в tooltip. При недоступном atlas обе витрины
используют честный fallback, без копирования `.dds` или шрифтов в репозиторий.
Подробности: [M19](../tasks/M19.md).

В M20 добавлены source-backed `SInvItemPlace` read/write и staging переноса
actor-owned предметов между слотами, поясом и рюкзаком для оригинальных
SoC/CS/CoP. Все три локальных корпуса разбираются без ошибок; exact anchor и
round-trip проходят, но M10 game load/re-save нового place ещё не выполнялся.
Подробности: [M20](../tasks/M20.md) и [XRAY placement evidence](../evidence/XRAY_PLACEMENT_2026-09-16.md).

В M21 добавлен read-only reader official S2 prototype CFG: точные SID,
категории, вес, max stack, equipment slot и upgrade SID; он подключён к
desktop source discovery и shared browser bundle contract. S2 compact
`type_key` пока не связан с prototype SID, поэтому add/clone/upgrade writer не
открыт. S2 не установлен на текущем хосте, статический `web/catalogs.json` не
расширялся догадочными данными. Подробности: [M21](../tasks/M21.md) и [S2 catalog
evidence](../evidence/S2_CATALOG_2026-09-16.md).

В M22 появился воспроизводимый read-only анализ нескольких S2 сейвов. На
доступном corpus есть 34 общих handle; у 13 меняется compact `type_key`, а
`052000` встречается у двух разных handle. В M25 добавлено чтение embedded
save-local name table: все parsed inventory rows доступных четырёх S2 samples
получили наблюдаемое имя (`25/25`, `36/36`, `34/34`, `34/34`). Это не
подтверждает переносимый SID-based constructor и не открывает S2 Add/clone/
upgrade writer, но UI больше не скрывает уже сериализованные имена за
`Неизвестный объект`. Подробности: [M22](../tasks/M22.md) и [S2 mapping
evidence](../evidence/S2_MAPPING_2026-09-16.md).

В M23 structural X-Ray `deep detach` получил read-only preflight по известным
`object_id`/`parent_id` edges: actor-owned leaf можно удалить, а explicit
equipped, direct dependent и unresolved target блокируются до записи. Полный
opaque reference graph и game load/re-save не заявляются. Подробности:
[M23](../tasks/M23.md) и [X-Ray delete evidence](../evidence/XRAY_DELETE_2026-09-16.md).

В M24 тот же decision появился per-item в общем snapshot: Qt и web отключают
удаление до staging и показывают причину blocker, а generated browser bundle
включает новый модуль. Batch-анализ parent map не делает snapshot квадратичным.
Подробности: [M24](../tasks/M24.md) и [X-Ray delete UI evidence](../evidence/XRAY_DELETE_UI_2026-09-16.md).

Actions включены. Матрица `tests` зелёная на Linux и Windows, `standalone-build`
собирает обе цели, packaged diagnostic проходит на самом Windows-раннере.
Разбор всех находок: [CI_AND_WINDOWS](../evidence/CI_AND_WINDOWS_2026-09-14.md).
Остался единственный блокирующий гейт, который машина выполнить не может:
запустить `SaveEditor.exe` на живом Windows-десктопе и проверить окно, масштаб
и клавиатуру.

Implementation B01 принят через [PR #44](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-2-HoC---Save_Editor/pull/44),
merge `3346167`. Текущий рабочий проход — B02: acceptance matrix находится в
[`docs/evidence/BETA_ACCEPTANCE.md`](../evidence/BETA_ACCEPTANCE.md), release
остаётся `blocked` до Windows/runner/DPI evidence.
