# Linux/Windows Save Editor — проектное решение

Статус: план по поручению владельца, 2026-09-13. Реализацию выполняет GPT-5.6 Luna по карточкам. Разработка новых функций в импорт не входит.

## Продукт и платформы

Одна настольная программа: открыть локальный файл или выбрать Steam Cloud save → увидеть поддерживаемые данные → подготовить изменения → проверить preview → backup → сохранить копию или загрузить в выбранный cloud slot → показать проверенный результат и путь восстановления.

Целевые платформы первой beta: **Windows 11 x64 и Ubuntu 22.04/24.04 x86_64**. Python разработки: **3.11 и 3.12**; первоначальная binary build lane — **3.11**. Windows 10, ARM64, macOS и произвольные Linux-дистрибутивы не входят в проверенный baseline beta. Расширять матрицу только отдельной задачей с результатами тестов.

Существующая v0.3 требует Python 3.10+ по синтаксису; это не обещание поддержки всех таких интерпретаторов. Конечному пользователю устанавливать Python не потребуется в packaged builds.

## Варианты интерфейса

| Подход | Плюсы | Издержки | Решение |
|---|---|---|---|
| Оставить Tkinter/ttk | Минимальные зависимости | Много ручной работы с таблицами, DPI, моделями, сигналами; второй набор UI-кода | **Удалён** после достижения Qt parity: два интерфейса расходились, а fallback никем не использовался |
| Python + PySide6/Qt Widgets | Один язык с ядром; таблицы/model-view, worker signals, native dialogs | Размер дистрибутива, Qt plugins и packaging | **Выбран**, единственный интерфейс |
| Tauri/Electron + web UI | Богатая веб-вёрстка | Второй стек, IPC и packaging Python sidecar | Не для десктопа; отдельный веб-вариант рассматривается как самостоятельная поставка того же ядра |

Один интерфейс и один набор правил правки. Веб-сервер, аккаунты приложения и
облачный backend для десктопной поставки не требуются.

## Границы модулей

`cli.py`, `save_format.py` и `steam_cloud.py` остаются совместимыми entry
points. Новые модули вводить только в соответствующей карточке:

```text
editor/models.py          immutable request/source/result types
editor/storage.py         backup, atomic export, local stale protection
editor/transactions.py    transport-independent cloud state machine
editor/service.py         inspect / prepare / export / upload orchestration
editor/codec.py           platform decoder resolution
editor/platforms.py       user data paths / helper discovery
ui/main_window.py          Qt navigation and selection
ui/inventory_model.py      table/filter model with stable handles
ui/changes_view.py         preview and operation progress
ui/backups_view.py         journal and restore
ui/cloud_view.py           source selection / sync states
packaging/                 reproducible platform builds and diagnostic entrypoint
```

Не разносить save_format.py по новым пакетам во время UI migration. CPU/IO работа идёт вне UI thread; UI получает immutable snapshots/events через сигналы. Никаких чтений Qt-виджетов из фонового потока.

## Контракты для первых задач

Ниже проектируемые API, в текущем baseline их ещё нет. S02 фиксирует models; следующие задачи импортируют их, а не создают несовместимые дубликаты.

```python
@dataclass(frozen=True)
class SourceRef:
    kind: Literal["local", "cloud"]
    locator: str   # absolute local path or exact remote path
    sha256: str

@dataclass(frozen=True)
class EditPlan:
    source: SourceRef
    money: int | None = None
    stacks: tuple[tuple[int, int], ...] = ()
    moves: tuple[tuple[int, int, int], ...] = ()
    detach: tuple[tuple[int, bool], ...] = ()
    attach: tuple[tuple[int, int, int, int, int], ...] = ()
    raw: tuple[RawPatch, ...] = ()
    upgrades: tuple[tuple[int, tuple[str, ...]], ...] = ()
    placements: tuple[tuple[int, str, int | None], ...] = ()

@dataclass(frozen=True)
class PreparedEdit:
    plan: EditPlan
    data: bytes
    output_sha256: str

@dataclass(frozen=True)
class ExportReceipt:
    output_path: Path
    backup_path: Path
    output_sha256: str

@dataclass(frozen=True)
class BackupRecord:
    journal_path: Path
    backup_path: Path
    created_at: str
    source_path: str
    source_sha256: str
    output_path: str | None
    output_sha256: str | None
    operation: dict[str, object]
    status: Literal["verified", "missing", "corrupt"]
    actual_sha256: str | None = None
    error: str | None = None

@dataclass(frozen=True)
class RestoreReceipt:
    output_path: Path
    backup_path: Path
    output_sha256: str

@dataclass(frozen=True)
class CloudReceipt:
    status: Literal["verified", "uncertain"]
    remote_path: str
    backup_path: Path
    recovery_path: Path
    output_sha256: str
    reason: str | None = None
```

S02: `prepare_edit(data: bytes, plan: EditPlan) -> PreparedEdit` verifies source hash and rejects raw with attach/detach before calling existing patch_save. S03: `export_local(source_path: Path, output_path: Path, prepared: PreparedEdit, backup_dir: Path) -> ExportReceipt` rejects stale source and same-path exports by default. S06: `upload_cloud(worker: CloudTransport, prepared: PreparedEdit, backup_dir: Path) -> CloudReceipt`; remote path comes only from plan.source, failures before write raise an error, ambiguous outcomes after write return uncertain without automatic retry. CloudTransport provides read_file, write_file, sync, wait_persisted, list_files with existing worker meanings.

Для оригинального X-Ray `EditPlan.upgrades` содержит уникальные пары
`(handle, tuple[serialized_upgrade_id, ...])`. Writer открывает эту операцию
только для release-scoped каталога официальных ресурсов и только для
подтверждённого `m_upgrades` vector; уже записанный неизвестный ID можно
сохранить или удалить, но новый ID без exact catalog/applicability не
принимается. Браузер только staging/preview/download, desktop replacement
проходит обычный M16 backup/read-back pipeline.

Для оригинального X-Ray `EditPlan.placements` содержит уникальные тройки
`(handle, placement_type, slot_id)`, где `placement_type` равен `slot`, `belt`
или `ruck`; `slot` требует номер 1…13, а `belt`/`ruck` используют `None`.
Writer меняет только подтверждённое `SInvItemPlace` в actor-owned client-data
по release-specific offset. Поле доступно как experimental capability только
для original SoC/CS/CoP с точным client-data anchor; неизвестный или
неподтверждённый place остаётся read-only. Qt и web используют один этот
immutable plan, показывают before → after, а preview/backup/read-back guards
остаются обязательными.

Для S.T.A.L.K.E.R. 2 официальный loose resource tree может дать отдельный
read-only metadata catalog: prototype SID, category, weight, max stack, slot и
upgrade SID. Desktop and an explicitly generated browser bundle carry these
metadata fields. Prototype SID не равен compact `type_key` из `.sav` без отдельного
mapping evidence; поэтому такой каталог не включает `serialization_family`,
prototype bytes или право add/clone/upgrade. Browser принимает этот
release-scoped metadata bundle только когда он явно сгенерирован из official
resource root; сайт не получает доступ к локальной папке игры автоматически.

Equipment Editor использует один shared projection для Qt и web. Пользовательские
категории `weapon`, `armor` и `helmet` не подменяют format-specific serializer
family; location (`equipped`/`inventory`) и точные catalog names/icons остаются
отдельными полями. Для original X-Ray прочность и bulk repair имеют maturity
`experimental` до game load/re-save evidence. Для S2 condition writer,
placement, add/remove и upgrades остаются `research` или `unsupported`, то есть
read-only с конкретной причиной; scalar observation не включает запись. Каждая
Enhanced Edition имеет независимый unavailable profile и не наследует writer
оригинальной игры.

Для original X-Ray `EditPlan.detach` остаётся явно structural операцией. Перед
удалением writer запускает `editor.xray_delete.analyze_xray_delete(...)` и
отказывает для отсутствующего/unresolved target, explicit equipped placement,
не-actor-owned record и любого parsed registry child по `parent_id`. Этот
preflight не извлекает ссылки из opaque STATE/UPDATE и не доказывает quest
семантику или game load/re-save; отсутствие decoded placement не считается
доказательством, что предмет экипирован.

`InventoryItem` дополнительно может нести `remove_editable` и `remove_reason`.
Для X-Ray они строятся тем же preflight в одном проходе по parsed registry;
Qt и web используют эти поля только для объяснимого staging guard. Это не
заменяет повторную проверку в writer и не открывает удаление для S2, Enhanced
или другого формата без capability `remove_items`.

M22 добавляет `editor.s2_mapping.analyze_s2_samples(...)` как read-only
evidence helper. Он сравнивает handle/type-key observations между явно
переданными samples, возвращает только hashes/агрегаты и всегда оставляет
mapping status `unconfirmed`; public SID не присваивается по совпадению ключа.
CLI-анализатор не пишет сейвы и не входит в browser runtime. Confirmed mapping
по-прежнему требует SID-labelled controlled save pair и game load/re-save.

U01: `EditorService.inspect(data: bytes) -> SaveInfo`, `.prepare(data: bytes, plan: EditPlan) -> PreparedEdit`, `.export_local(...) -> ExportReceipt` and `.upload_cloud(...) -> CloudReceipt` forward to these common implementations. U05 adds `inspect_backup`, `list_backups` and `.restore_local(...) -> RestoreReceipt`; only `verified` records can be restored. Dependencies must be injectable for tests; service imports no UI.

## Запись и отмена

Инварианты: exact source SHA → unique verified backup → prepare/CRC/round-trip → output recovery copy → actual write → verification. Preview связан с теми же bytes и SHA, которые применяются. Повторное изменение формы требует нового preview.

Сейчас выбрать простой запрет raw + attach/detach в одной операции; relocatable raw addressing — отдельное будущее расширение, не угадывать новые offsets. RAW хранит expected original context в evidence, не называется durability.

Local desktop: после одного явного подтверждения основная кнопка «Сохранить»
атомарно заменяет открытый слот; до записи создаётся verified backup, а
preview, CRC/SHA и fresh-source проверки остаются внутренними. Технический
export новой копии сохраняется в общем service/CLI API, но не является частью
обычного Qt flow. Backup создаётся exclusively и не перезаписывается; before/
after hashes в JSON journal. После падения исходник доступен. Не обещать fsync
directory на ОС без поддержки; документировать пределы durability.

Cloud: перед записью повторно сравнить SHA; один upload за раз. Steam API не даёт нам атомарного compare-and-swap, поэтому остаётся окно внешней записи: GFN должен быть закрыт. Timeout после WriteFile означает «результат неизвестен», не «ничего не записано» и не «успех». Автоповтор upload запрещён. Restore проходит тот же preview/backup/verify pipeline. До WriteFile отмена безопасна; после отправки — продолжить проверку статуса, не обещать rollback.

## UI specification

Основной язык — русский; внутренние ID показывать только в деталях, переводы оставлять в ресурсах. Resizable layout, keyboard navigation, видимые focus states, масштаб 100/150/200%, проверки на 1366×768 и 1920×1080.

U07 фиксирует визуальный слой Qt: `ui/theme.py` задаёт charcoal/olive/rust
palette через стандартный Fusion/QSS, а `MainWindow` собирает title bar,
metadata/status bar, sidebar и snapshot-backed metric cards. Макет не является
источником игровых данных: неизвестные поля остаются `—`, а filename, SHA,
CRC, money и inventory берутся только из текущего `SaveInfo`; полная UE5 GVAS
schema пока не подтверждена и не отображается как распознанная.

```text
[Открыть .sav] [Steam Cloud]                         [Настройки]
Сейв: имя • дата • источник • поддержка формата
[Обзор] [Инвентарь] [Изменения (2)] [Резервные копии]

Купоны: 56 995       Новое значение: [900 000]
[Поиск предметов] [Категория] [Только изменённые]
Предмет / категория | Количество | Вес | Статус поддержки
Выбранный предмет: текущее → новое; причина read-only

Для ЧС/ЗП при подтверждённом векторе: текущие улучшения → каталоговые
варианты; неизвестные уже записанные ID явно отмечены и не предлагаются для
добавления.

[Сбросить изменения]                         [Сохранить]
```

Название неизвестного предмета: «Неизвестный предмет · 0x…»; не выдумывать human names из type-key. Пока нет доказанного SID mapping, каталог доступен как справочник, а Add не активен.

Preview, путь назначения, backup path и before→after остаются внутренними
техническими данными. Пользователь видит один status flow: проверка → backup →
запись → подтверждение; ошибки понятным текстом с раскрываемыми technical
details и кнопкой копирования отчёта без credentials/save bytes. Cloud tab
требует явного connect/list/analyze; показывает только `Data/*.sav`, закрепляет
выбранный remote locator и отображает `verified`/`uncertain` receipt. После
`WriteFile` повторная запись из того же preview запрещена.

Experimental lab скрыт по умолчанию за отдельным включением в настройках. Пользователь должен отличать detach от delete. Grid view сначала read-only; drag-and-drop mutation не входит в первую Qt parity beta. Текущие move/detach/attach/raw остаются доступны явно как experimental, CLI сохраняется.

## Исследовательские gates

SID mapping: несколько независимых контролируемых пар и точные источники config; public SID != bytes in save. Durability: тот же handle в трёх известных состояниях + игровая загрузка/повторный save. Registry: доказанные границы/count/allocator и ссылки, не окно до следующего известного handle. Clone/Add/Delete/attachments разрешаются только после соответствующего evidence gate. Если данные не получены, результат research-задачи — документированный blocker с конкретным запросом, а не фиктивная кнопка.

## Проверенные внешние основания

Проверено 2026-09-13: [pyooz 0.0.8](https://pypi.org/project/pyooz/0.0.8/) публикует win_amd64 и manylinux x86_64 wheels; это не доказательство запуска нашего приложения на Windows. [Qt + PyInstaller](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html) описывает упаковку PySide6. [PyInstaller](https://www.pyinstaller.org/en/stable/) требует собирать отдельно на целевых ОС; B01 закрепляет `PyInstaller==6.22.3` и добавляет onedir spec/manifest/checksum flow. [SteamCloudFileManager](https://github.com/Fldicoahkiin/SteamCloudFileManager) — внешний helper; совместимость конкретного --steam-worker протокола должна быть проверена по pinned release в P02/S06.
