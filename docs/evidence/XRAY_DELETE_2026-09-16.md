# X-Ray deletion safety — 2026-09-16

## Вывод

M23 не объявляет общий «удалить любой предмет» безопасным. Он усиливает
существующий structural `EditPlan.detach` проверками, которые действительно
видны в разобранном X-Ray object registry:

- target должен быть actor-owned;
- explicit `storage == equipped` блокируется;
- каждый parsed object с `parent_id == target.object_id` считается зависимым;
- отсутствующий или `unresolved` target блокируется до записи.

Если эти условия выполнены, writer удаляет только точный record window и
обновляет OBJECT count существующим container writer. Backup, source SHA,
rebuild и read-back guards остаются без изменений.

## Что считается известной ссылкой

В parsed `XRayObject` уже есть `object_id` и `parent_id`, считанные из строгого
object-record envelope. Поэтому непосредственный registry child можно назвать
по точному handle и не удалять родителя в обход него. Это не заменяет полного
reference graph: поля внутри STATE/UPDATE, quest ownership, equipment links,
prototype identity и неизвестные хвосты сохраняются opaque и не сканируются
эвристически.

`storage is None` означает, что placement anchor не был разобран. Для
совместимости с ранними read-only fixtures такой объект не объявляется
экипированным автоматически; отдельное подтверждение его game semantics всё
ещё требуется.

## Проверки

Synthetic regression покрывает четыре результата: actor-owned leaf проходит;
explicit equipped object отклоняется; parent с child отклоняется с точным
dependent handle; missing object возвращает blocked analysis. Writer tests
подтверждают отказ до registry rebuild для equipped и dependent cases.
Browser bundle manifest также проверяет, что новый общий модуль поставляется
вместе с `xray_save`, поэтому web import graph не расходится с desktop core.

Личные сейвы не изменялись и в evidence не включались. Game load/re-save не
выполнялся, поэтому M10 и полная R08 acceptance остаются открытыми.
