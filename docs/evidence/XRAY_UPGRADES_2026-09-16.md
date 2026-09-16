# X-Ray upgrades — 2026-09-16

Этот файл фиксирует только подтверждённую границу исследования. Моды,
личные сейвы, байты сейвов и персональные пути в Git не попадают. Запуск игры,
загрузка изменённого сейва и повторное сохранение по M10 не выполнялись.

## Схема из исходников

В публичном исходнике [OpenXRay xray-16, inventory item STATE
codec](https://github.com/OpenXRay/xray-16/blob/c37860c09850d894b721ba115cd936bb3f11482c/src/xrServerEntities/xrServer_Objects_ALife_Items.cpp#L79-L95)
`CSE_ALifeInventoryItem::STATE_Write` записывает `m_fCondition`, затем
`m_upgrades`; `STATE_Read` читает `m_upgrades` только при
`m_wVersion > 123`. `m_upgrades` имеет тип `xr_vector<shared_str>`, поэтому
общий сериализатор вектора даёт `u32 count` и последовательность
нуле-терминированных строк. Реализация редактора меняет только этот bounded
vector и сохраняет последующий STATE-хвост, UPDATE и соседние записи.

Отсутствие вектора до этой version boundary не трактуется как пустой список:
для SoC и ранних состояний CS поле остаётся `None` и read-only. Это различие
важно для ЧН, где в одном реальном корпусе встречаются actor-owned vectors,
а в другом состоянии ещё может не быть подтверждённой границы.

## Локальный read-only probe

Проверены копии официальных оригинальных релизов без записи в исходные файлы.
Ниже агрегаты конкретного корпуса, а не универсальные характеристики каждой
установки:

| Релиз | Catalog definitions | Actor-owned vectors | Positive vectors | Stored IDs matching catalog | Stored IDs outside catalog |
| --- | ---: | ---: | ---: | ---: | ---: |
| Shadow of Chernobyl | 0 | 0 | 0 | 0 | 0 |
| Clear Sky | 503 | 75 | 3 | 7 | 9 |
| Call of Pripyat | 654 | 132 | 3 | 38 | 0 |

Каталог для новых значений release-scoped и item-scoped: редактор не выводит
чужие ID и не превращает неизвестную строку из сейва в официальное описание.
Уже записанные неизвестные ID можно оставить в векторе или снять галочку;
добавить их заново нельзя.

## Реализация и граница

- `parse_xray` возвращает vector, абсолютные границы и признак
  `upgrades_editable` только для подтверждённого actor-owned объекта.
- `EditPlan.upgrades` принимает уникальные handle и уникальные строки;
  writer проверяет release, catalog и applicability перед записью.
- Qt и web показывают текущий vector, каталоговые варианты и staged before →
  after; исходные bytes не меняются до Preview.
- Desktop запись требует M16 backup/read-back; browser скачивает новую копию.
- Возможность помечена `experimental_fields`. Structural round-trip не
  доказывает, что конкретная версия игры примет новый upgrade, покажет его в
  меню или сохранит после следующего игрового save.

## Источник и тесты

Порядок полей взят из исходника X-Ray, а vector boundary и сохранение хвоста
проверяются синтетическим корпусом в `tests/test_xray_upgrades.py`. Web bridge
и UI staging проверяются в `tests/test_web_upgrades.py` и
`tests/test_ui_upgrades.py`; последний пропускается, если Qt test runtime не
установлен.
