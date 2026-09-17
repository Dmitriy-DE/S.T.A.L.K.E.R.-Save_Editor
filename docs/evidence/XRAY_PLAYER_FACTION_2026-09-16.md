# X-Ray player community — 2026-09-16

Этот файл фиксирует исследование принадлежности игрока к группировке в
официальной оригинальной трилогии. Моды, личные файлы и байты сейвов в Git не
попадают. Проверка игровым запуском и повторным сохранением не выполнялась.

## Схема из исходников

В публичном исходнике [OpenXRay xray-16](https://github.com/OpenXRay/xray-16)
`CSE_ALifeCreatureActor::STATE_Write` сериализует сначала состояние creature,
затем `CSE_ALifeTraderAbstract::STATE_Write`. В trader STATE после `m_dwMoney`
идут `specific_character`, trader flags, profile, затем три signed `s32`:
`m_community_index`, `m_rank`, `m_reputation`; после них сохраняются имя и
deadbody flags. Поэтому редактор не ищет похожее число по payload, а проходит
тот же version-gated prefix и принимает community только с подтверждённым
offset.

Каталог community не выводится из текущего числа в сейве. Для каждой игры
используется её отдельный resource-derived faction catalog с numeric id; ключ,
которого нет в каталоге или у которого нет numeric id, writer отклоняет.

## Read-only probe корпуса

Проверены копии официальных сейвов трёх установленных релизов без записи в
исходные файлы:

| Релиз | Actor community | community offset подтверждён |
| --- | ---: | --- |
| Shadow of Chernobyl | 0 | да |
| Clear Sky | 4 | да |
| Call of Pripyat | 0 | да |

Это значения конкретных проверенных слотов, а не универсальное состояние
кампании. S.T.A.L.K.E.R. 2 и Enhanced Editions остаются read-only: для них нет
подтверждённой offline-схемы actor community.

## Реализация и граница

- `parse_xray` возвращает текущий signed `s32`, его bounded offset и флаг
  редактируемости.
- `EditPlan.player_faction` принимает только release-scoped catalog key.
- Writer меняет только четыре байта actor community, затем пересобирает
  контейнер и проверяет round-trip; остальные actor поля сравниваются тестом.
- Qt и web показывают текущую группировку, staged выбор и конкретное
  предупреждение о возможной перезаписи сюжетными скриптами. Web скачивает
  копию и не меняет исходный файл.
- Поле отмечено `experimental_fields`; структурный round-trip не доказывает,
  что сюжет сохранит принадлежность после загрузки. Контролируемое
  load/re-save по M10 остаётся отдельным незавершённым gate.
