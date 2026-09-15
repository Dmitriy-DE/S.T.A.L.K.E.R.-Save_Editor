# M01 — Реестр форматов сохранений: дизайн

## Цель

Ввести один UI-free реестр форматов, через который `EditorService` выбирает
парсер и подготовку правок. В M01 в реестре будет ровно один адаптер:
`stalker2`, делегирующий существующим `save_format.inspect_save` и
`editor.prepare.prepare_edit`. Формат X-Ray в этой карточке не добавляется.

## Границы

В работу входят `editor/formats.py`, выбор формата в `editor/service.py`,
передача `format_id` и `format_title` в локальный и Steam Cloud snapshots, а
также синтетические regression-тесты. `save_format.py`, `EditPlan`,
`PreparedEdit`, storage, CRC, SHA-проверка и алгоритм round-trip остаются без
изменения поведения.

## Архитектура

`editor.formats` содержит структурный `SaveFormat` Protocol:

```python
class SaveFormat(Protocol):
    id: str
    title: str

    def detect(self, data: bytes) -> bool: ...
    def inspect(self, data: bytes, *, with_inventory: bool = True) -> SaveInfo: ...
    def prepare(self, data: bytes, plan: EditPlan) -> PreparedEdit: ...
```

`Stalker2Format` — единственный зарегистрированный экземпляр. Его `inspect`
вызывает `inspect_save`, `prepare` вызывает `prepare_edit`, а `detect` вызывает
существующий инспектор в read-only режиме и принимает только контейнер с ровно
одной подтверждённой S.T.A.L.K.E.R. 2 money-anchor. Любая ошибка разбора
чужих или обрезанных байтов превращается в `False`; исключения из `detect` не
выходят наружу.

Реестр предоставляет `register`, `formats`, `by_id` и `detect`. Начальная
регистрация выполняется статически при импорте модуля; дубликаты ID отклоняются,
а `formats()` возвращает неизменяемый tuple. `detect()` возвращает найденный
формат или `None` и не выбирает первый формат по умолчанию.

`EditorService.inspect` и `.prepare` сохраняют текущие return types. Внутренний
`inspect_result` возвращает формат и `SaveInfo`, чтобы worker не распознавал
один файл повторно. `LocalSnapshot` и `CloudSnapshot` получают `format_id` и
`format_title` с совместимыми значениями по умолчанию для существующих тестовых
конструкторов. Прямой `save_format.inspect_save` продолжает возвращать тот же
`SaveInfo`, что и сервис; идентификатор формата хранится на уровне snapshot, а
не добавляется в существующий parser model.

## Поток данных

1. Worker получает bytes.
2. `EditorService.inspect_result` вызывает registry `detect`.
3. Найденный формат выполняет `inspect`; сервис возвращает `SaveInfo` и
   metadata формата.
4. UI публикует immutable snapshot с теми же bytes, `SaveInfo`, ID и title.
5. При подготовке правки сервис повторно выбирает формат по содержимому и
   вызывает его `prepare`; для S2 это существующий immutable `EditPlan` path.

Инъектируемые `inspect_fn` и `prepare_fn` сохраняются как test seams. При
отсутствии подмены production path всегда проходит через registry.

## Ошибки и обратная совместимость

Неизвестный формат в M01 даёт `SaveError` на сервисных `inspect`/`prepare` с
нейтральным сообщением; подробный общий отказ с размером и списком поддержанных
форматов относится к M02. `by_id` для неизвестного ID поднимает `KeyError`.
Существующие прямые вызовы `save_format` и CLI остаются рабочими.

## Проверки приёмки

- В реестре ровно один формат с ID `stalker2`.
- Synthetic fixture определяется этим форматом.
- Произвольные неизвестные bytes дают `None`, не исключение и не первый формат.
- `EditorService.inspect` совпадает с прямым `inspect_save` по `SaveInfo`.
- `EditorService.prepare` выдаёт те же bytes и SHA, что существующий
  `prepare_edit`/`patch_save` путь.
- Local и Cloud snapshots несут `format_id`/`format_title`.
- `make check` и `make test` проходят.

