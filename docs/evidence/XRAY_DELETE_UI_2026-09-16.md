# X-Ray delete safety in UI — 2026-09-16

## Граница

M24 переносит M23 decision в общий inventory snapshot. Для оригинального
X-Ray предмета `remove_editable` вычисляется тем же `object_id`/`parent_id`
preflight, что и writer:

- actor-owned leaf — кнопка удаления доступна;
- explicit equipped — кнопка отключена и причина содержит blocker;
- parsed dependent child или unresolved target — кнопка отключена;
- отсутствие placement не считается экипировкой автоматически.

Это только UX-предохранитель. `prepare_xray` повторяет проверку непосредственно
перед registry rebuild, поэтому внешний caller не может обойти UI одним
staged JSON plan.

## Qt и web

Qt показывает per-item reason в label выбранного предмета и не создаёт
`staged_detach` для blocked row. Web передаёт `remove_editable/remove_reason`
через bridge, отключает кнопку и оставляет reason в tooltip; исходные bytes и
state не меняются до Preview.

Новый `editor/xray_delete.py` включён в generated `web/pysrc.json`. Batch helper
строит карту parent → children одним проходом, сохраняя пригодность для
крупных CoP snapshots.

## Проверки и ограничения

Synthetic/Qt/bridge/static tests покрывают enabled leaf и blocked equipped
object. Личные сейвы не изменялись, game load/re-save не выполнялся, а opaque
STATE/UPDATE и quest references остаются за M23/R08 reference-graph gate.
