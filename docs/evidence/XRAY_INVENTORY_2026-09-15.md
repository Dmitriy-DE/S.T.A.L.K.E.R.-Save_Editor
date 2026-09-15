# X-Ray inventory writer evidence — 2026-09-15

Эта запись содержит только агрегированные read-only результаты. Байты личных
сейвов, их имена, SHA и пути в репозиторий не добавлялись; writer не сохранял
результат ни в один игровой каталог.

## Что подтверждено

Для original Steam-корпуса на текущем Linux-хосте каждый уникальный файл был:

1. распакован и строго проверен через полный object registry;
2. проверен на byte-for-byte no-op через `XRayContainer.build()`;
3. проверен in-memory money round-trip на одном representative save каждого
   релиза;
4. проверен in-memory ammo count round-trip одновременно в STATE и UPDATE на
   одном representative save каждого релиза.

| Release | Files | Unique bytes | Strict parse | No-op | Actor version | Object count | Inventory count | Money | Ammo |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| Original Shadow of Chernobyl | 4 | 4 | 4 | 4 | 118 (4) | 16,788–20,010 | 5–87 | 1/1 | 1/1 |
| Original Clear Sky | 56 | 56 | 56 | 56 | 124 (56) | 22,849–25,350 | 7–139 | 1/1 | 1/1 |
| Original Call of Pripyat | 168 | 168 | 168 | 168 | 128 (168) | 11,067–31,925 | 28–229 | 1/1 | 1/1 |

`Money` и `Ammo` показывают успешные representative in-memory проверки, а не
число файлов, изменённых на диске. Все 228 уникальных образцов имели пустой
error aggregate в этом прогоне.

## Structural slice

Сериализованный object теперь предоставляет проверенные окна `SPAWN`, `STATE`
и `UPDATE`, включая точные границы record. Writer умеет только доказанный
synthetic/catalog-backed класс:

- clone существующего подтверждённого ammo object с новым `object_id`;
- изменить serialized key и parent на actor;
- записать count в обе подтверждённые ammo позиции;
- добавить/удалить object record с корректным registry count и новым framing;
- выполнить строгий reparse результата.

Реальный установленный catalog SoC на этой машине пока не содержит доказанных
`prototype` bytes, поэтому добавление предметов в реальные saves не включено.
Каталог не используется как повод угадывать SID, prototype или поля
durability/upgrades. Остальные item classes, inventory grid/position и
detach без deep-remove остаются read-only.

## Ограничения

- Результаты относятся к обнаруженному на этой машине original-корпусу и не
  являются доказательством Enhanced Editions, Windows runtime или загрузки
  результата самой игрой.
- Повторное сжатие после изменения может иметь другие packed bytes; no-op
  обязан быть byte-identical, а изменённый output подтверждается parse и SHA.
- Игровой load/re-save и controlled real-save add/remove остаются отдельным
  внешним acceptance gate.
