# Support UI evidence — 2026-09-16

## Визуальный источник

Пользовательский референс — [stalker-new-arsenal-7-spawner](https://github.com/thinkawitch/stalker-new-arsenal-7-spawner).
В его README указано, что экран описан в
`gamedata/config/ui/ui_cheat_soc.xml`; в самом XML используются фон/рамки
`ui_menu_options_dlg` и `ui_tablist_textbox`, кнопочные текстуры
`ui_inGame2_Mp_bigbuttone_noupcorner`, `ui_button_main02`/`ui_button_main03`,
шрифты `graffiti19`/`letterica16` и песочно-жёлтые текстовые состояния:
[UI XML](https://github.com/thinkawitch/stalker-new-arsenal-7-spawner/blob/master/gamedata/config/ui/ui_cheat_soc.xml#L519-L749).

В Save Editor перенесены визуальные принципы, а не игровые assets:

- компактная кнопка справа в верхней строке;
- тёмная charcoal-панель с ржавой рамкой;
- жёлто-песочные заголовки и значения, отдельное состояние hover/focus;
- короткие строки method → value → action без перегрузки окна.

Игровые `.dds`, fonts и UI XML в репозиторий не копируются: desktop использует
существующий Qt Fusion/QSS, web — локальный CSS с той же palette. Это не
добавляет зависимости и не требует сети после загрузки страницы.

## Поведение

Кнопка `♡ Support project` находится в верхнем правом углу desktop title bar и
web header. Она открывает локальный modal/dialog; перехода на PayPal, Binance
или другой внешний адрес нет.

В диалоге отображаются только заданные пользователем реквизиты:

- PayPal: `breygel.dima@gmail.com`;
- Binance Pay: `434350727` с подписью `Binance ID`;
- USDT: TRON (TRC20), адрес `TF5hpkAmF9vjbpaRpJ5ewpbCC122jED1ds`.

Каждый value копируется отдельной кнопкой `Copy`, после успешной операции
кнопка на короткое время показывает `Copied`. Нет payment API, backend,
authentication, tracking, analytics, QR-кодов, startup popup или recurring
reminder.

## Проверка и ограничения

`tests/test_support_ui.py` проверяет три clipboard values, feedback, открытие
application-modal Qt dialog и наличие локального web modal. Автоматические
платежи не реализованы и не проверяются; это намеренно статическая контактная
информация.
