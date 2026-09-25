# Официальные источники по моддингу и API для внутриигрового компаньона

Черновик собран Gemini (RS-2, MOD-1) 2026-09-25, выборочно проверен Claude.
Статус утверждений: **проверено** — прочитан первоисточник; остальное — со
ссылкой, но не перепроверено.

## Выводы для роадмапа

- **S2:** Blueprint-мод работает только в загруженном мире (`ModWorldSubsystem`
  → `OnWorldBeginPlay`). **Проверено** по PDF GSC: «the moment the player loads
  into the map (… not in the main menu)». Окно в главном меню официальным API не
  делается, а оверлей в игре — стандартный UMG. Предметы и деньги можно выдавать
  через `Execute Console Command` (например, спавн по SID). Итог: компаньон S2 —
  окно в игре (MOD-4), не в главном меню.
- **EE:** в Steam Workshop разрешены скрипты `.script` и конфиги `.ltx`/`.xml`,
  запрещены `.dll`/`.exe`. Упаковка через `xrCompress -store` в `.pak`, загрузка
  через `xrSWS_Upload`. На mod.io скрипты запрещены. Итог: Lua-компаньон для EE
  возможен только через Steam Workshop (MOD-3).
- **Оригиналы:** официальные X-Ray SDK — ТЧ 0.4, ЧН 0.5/0.6, ЗП 0.7.
  Вся нужная Lua-функциональность есть:
  - `db.actor:give_money`; в ТЧ отрицательные суммы ненадёжны;
  - `alife():create(..., parent_id)` и `alife():release(se_obj, true)`: только серверный объект;
  - `set_condition`;
  - `relation_registry.set_community_goodwill`, `set_character_rank`;
  - `set_actor_position` — только в пределах уровня;
  - между уровнями — динамический `level_changer`, созданный через `alife():create` с заполненным net_packet.
- **Горячая клавиша:** в ванильном X-Ray нет глобального коллбэка клавиш во время игры. Открытие через `OnKeyboard` в `ui_main_menu.script`: Esc, затем клавиша.

## S.T.A.L.K.E.R. 2 (Zone Kit)

PDF GSC на `https://cdn.stalker2.com/guides/`:

- `Game_Features_Modding_Guide.pdf`;
- `Intro_to_actor_&_placeholder_mods.pdf`;
- `Simple_mod_dependency_system.pdf`;
- `How_to_add_new_actors.pdf`;
- `How_to_patch_vanilla_actors.pdf`;
- `How_to_delete_vanilla_actors.pdf`;
- `Audio_modding_quick_start_guide.pdf`;
- `How_to_apply_modifications_to_vanilla_.cfg_files.pdf` — патчи `.cfg_patch_*`, полезно для CP-4/KB-7;
- `Save_Load_system_for_mods.pdf` — данные мода в сейве, до 10 МБ; **проверено**;
- `Launching_new_quest_in_game_build_using_ModWorldSubsystem.pdf` — **проверено**;
- `Mod_TextTool.pdf`.

Где ещё:

- Раздел поддержки: https://support.stalker2.com/hc/en-us/sections/36534422256017-The-Modder-s-Zone
- Zone Kit: https://store.epicgames.com/p/stalker-2-zone-kit.
  - Требования: Windows 10/11, 32 ГБ RAM, 8 ГБ VRAM, около 700 ГБ места.
  - Нужна лицензия игры.

## Enhanced Editions

- Гайд GSC: https://steamcommunity.com/sharedfiles/filedetails/?id=3497576322
- Инструменты:
  - https://modio.stalker-game.com/assets/tools-stk-lotz-modio.7z (xrCompress);
  - http://modio.stalker-game.com/assets/ee/stk-utils.7z (xrSWS_Upload);
  - https://modio.stalker-game.com/assets/ee/stk-shaders.7z (DX12-шейдеры, нужен DXC).

## Оригинальная трилогия

- ТЧ SDK 0.4: http://files.gsc-game.com/st/xray-sdk-setup-v0.4.exe
- ЧН SDK: http://files.gsc-game.com/st/xray-cs-sdk-setup.exe
- ЗП SDK 0.7: http://files.gsc-game.com:3128/st/xray-cop-sdk-setup.exe
- Документация: https://sdk.stalker-game.com/en/index.php?title=S.T.A.L.K.E.R._MOD_portal
- Привязки Lua (OpenXRay):
  - `src/xrGame/script_game_object_script{,2,3}.cpp`;
  - `alife_simulator_script.cpp`;
  - `level_script.cpp`;
  - `ui/UIScriptWnd_script.cpp`.

Ссылки файлового сервера GSC старые (HTTP): скачивать только владельцу и
проверять подпись и хеш установщика вручную.
