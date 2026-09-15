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
   одном representative save каждого релиза;
5. проверен in-memory catalog-backed add path и synthetic deep-remove
   regression без записи результата в игровой каталог.

| Release | Files | Unique bytes | Strict parse | No-op | Actor version | Object count | Inventory count | Money | Ammo |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| Original Shadow of Chernobyl | 4 | 4 | 4 | 4 | 118 (4) | 16,788–20,010 | 5–87 | 1/1 | 1/1 |
| Original Clear Sky | 56 | 56 | 56 | 56 | 124 (56) | 22,849–25,350 | 7–139 | 1/1 | 1/1 |
| Original Call of Pripyat | 168 | 168 | 168 | 168 | 128 (168) | 11,067–31,925 | 28–229 | 1/1 | 1/1 |

`Money` и `Ammo` показывают успешные representative in-memory проверки, а не
число файлов, изменённых на диске. Детальный verifier для всех профилей выдал:

```json
{
  "stalker2": {"candidates": 0, "parsed": 0, "sha_matches": 0},
  "stalker-soc": {"candidates": 4, "parsed": 4, "versions": {"118": 4}, "sha_matches": 4, "edit_roundtrips": 7},
  "stalker-cs": {"candidates": 56, "parsed": 56, "versions": {"124": 56}, "sha_matches": 56, "edit_roundtrips": 109},
  "stalker-cop": {"candidates": 168, "parsed": 168, "versions": {"128": 168}, "sha_matches": 168, "edit_roundtrips": 336},
  "stalker-soc-ee": {"candidates": 0, "parsed": 0},
  "stalker-cs-ee": {"candidates": 0, "parsed": 0},
  "stalker-cop-ee": {"candidates": 0, "parsed": 0}
}
```

Все 228 уникальных образцов имели пустой `failure_summaries`; verifier выводит
только агрегаты и не сохраняет пути, имена или байты.

## Structural slice

Сериализованный object теперь предоставляет проверенные окна `SPAWN`, `STATE`
и `UPDATE`, включая точные границы record. Writer умеет доказанный
synthetic/catalog-backed путь для следующих serializer families:

- `ammo` — clone существующего ammo object с новым `object_id`, serialized key,
  actor parent и count в обеих подтверждённых позициях;
- `base`, `detector`, `outfit`, `pda`, `torch`, `weapon`,
  `weapon_magazined`, `weapon_shotgun`, `weapon_wgl` — clone существующего
  registry template той же family с новым key/object id и actor parent;
- удалить любой выбранный actor-owned registry record только как `deep`
  operation;
- добавить/удалить object record с корректным registry count и новым framing;
- выполнить строгий reparse результата.

Установленные официальные каталоги дали 389 item definitions для SoC, 417 для
CS и 434 для CoP. В отдельном read-only прогоне на representative save каждого
релиза по одному item из всех десяти перечисленных families был добавлен в
память, результат распарсился обратно, а исходный SHA остался неизменным:

| Release | Catalog items | Families exercised | Added records |
| --- | ---: | ---: | ---: |
| Original Shadow of Chernobyl | 389 | 10 | 10 |
| Original Clear Sky | 417 | 10 | 10 |
| Original Call of Pripyat | 434 | 10 | 10 |

Это не копирование prototype bytes из game archive: каталог сообщает ключ,
категорию, stack limit и serializer family, а сериализованный STATE/UPDATE
template берётся из самого save. Каталог не используется для угадывания SID,
prototype или полей durability/upgrades. Inventory grid/position,
reference-safe deletion, attachments и game semantics остаются отдельными
ограничениями.

## Ограничения

- Результаты относятся к обнаруженному на этой машине original-корпусу и не
  являются доказательством Enhanced Editions, Windows runtime или загрузки
  результата самой игрой.
- Повторное сжатие после изменения может иметь другие packed bytes; no-op
  обязан быть byte-identical, а изменённый output подтверждается parse и SHA.
- Web-каталог содержит только metadata keys/families без игровых архивов,
  локальных путей и save bytes; desktop каталог читается из явно выбранных
  официальных ресурсов read-only.
- Игровой load/re-save и controlled real-save add/remove остаются отдельным
  внешним acceptance gate.
