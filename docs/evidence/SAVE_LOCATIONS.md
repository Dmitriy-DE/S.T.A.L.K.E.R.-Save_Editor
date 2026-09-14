# Save locations — M03 research evidence

Исследование выполнено 2026-09-15. В таблицу попали только пути, для которых
есть опубликованный источник. Папка считается найденной только если она уже
существует; discovery ничего не создаёт и не читает содержимое сейвов.

## Что подтверждено

| Игра и издание | Подтверждённый путь | Источник и проверка |
|---|---|---|
| S.T.A.L.K.E.R. 2, Windows/общий | `%LOCALAPPDATA%\Stalker2\Saved\SaveGames` | [PCGamingWiki: S.T.A.L.K.E.R. 2](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R._2%3A_Heart_of_Chornobyl), строка Save game data location; сверено с GOG/Steam строками той же таблицы. |
| S.T.A.L.K.E.R. 2, Steam | `%LOCALAPPDATA%\Stalker2\Saved\STEAM\SaveGames` | [PCGamingWiki: S.T.A.L.K.E.R. 2](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R._2%3A_Heart_of_Chornobyl), Steam row. |
| S.T.A.L.K.E.R. 2, GOG | `%LOCALAPPDATA%\Stalker2\Saved\GOG\SaveGames` | [PCGamingWiki: S.T.A.L.K.E.R. 2](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R._2%3A_Heart_of_Chornobyl), GOG row. |
| S.T.A.L.K.E.R. 2, Game Pass/Microsoft Store | `%LOCALAPPDATA%\Packages\GSCGameWorld.S.T.A.L.K.E.R.2HeartofChornobyl_6fr1t1rwfarwt\SystemAppData\xgs\<user-id>\SaveGames` | [PCGamingWiki: S.T.A.L.K.E.R. 2](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R._2%3A_Heart_of_Chornobyl), Microsoft Store row. `<user-id>` не угадывается: discovery перечисляет существующие каталоги под `xgs`. |
| Shadow of Chernobyl, оригинал/retail | `%PUBLIC%\Documents\stalker-shoc\savedgames` | [PCGamingWiki: Shadow of Chernobyl](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Shadow_of_Chernobyl), Windows row; страница отдельно перечисляет патчи 1.0004–1.0006. |
| Shadow of Chernobyl, GOG | `%USERPROFILE%\Documents\Stalker-SHOC\savedgames` | [PCGamingWiki: Shadow of Chernobyl](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Shadow_of_Chernobyl), GOG row. |
| Clear Sky, оригинал/1.5.10 | `%USERPROFILE%\Documents\Stalker-STCS\savedgames` | [PCGamingWiki: Clear Sky](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Clear_Sky), Windows row; там же 1.5.10 назван последним официальным патчем. |
| Clear Sky, GOG | — отдельная точная GOG path row не подтверждена | [PCGamingWiki: Clear Sky](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Clear_Sky) lists GOG, but its save table has no separate GOG row. The documented X-Ray Windows path remains a fallback probe, not a GOG-specific claim. |
| Call of Pripyat, оригинал/1.6.02 | `%PUBLIC%\Public Documents\S.T.A.L.K.E.R. - Call of Pripyat\savedgames` | [PCGamingWiki: Call of Pripyat](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Call_of_Pripyat), Windows row; страница описывает оригинал и указывает 1.6.02 GOG/Steam patches. |
| Call of Pripyat, GOG | `%USERPROFILE%\Documents\Stalker-COP\savedgames` | [PCGamingWiki: Call of Pripyat](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Call_of_Pripyat), GOG row. |
| Shadow of Chernobyl, Enhanced/Legends, GOG | `%USERPROFILE%\Saved Games\STALKER Shadow of Chornobyl - EE\gog\savedgames` | [PCGamingWiki: Shadow Enhanced](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Shadow_of_Chornobyl_Enhanced_Edition), GOG row. |
| Shadow of Chernobyl, Enhanced/Legends, Steam | `%USERPROFILE%\Saved Games\STALKER Shadow of Chornobyl - EE\STEAM\savedgames` | [PCGamingWiki: Shadow Enhanced](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Shadow_of_Chornobyl_Enhanced_Edition) and [SteamDB UFS](https://steamdb.info/app/2427410/ufs/) (app ID 2427410 and `WinSavedGames` path). |
| Clear Sky, Enhanced/Legends, Steam | `%USERPROFILE%\Saved Games\STALKER Clear Sky - EE\STEAM\savedgames` | [PCGamingWiki: Clear Sky Enhanced](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Clear_Sky_Enhanced_Edition) and [SteamDB UFS](https://steamdb.info/app/2427420/ufs/) (app ID 2427420 and `WinSavedGames` path). |
| Call of Pripyat, Enhanced/Legends, Steam | `%USERPROFILE%\Saved Games\STALKER Call of Prypiat - EE\STEAM\savedgames` | [PCGamingWiki: Call of Prypiat Enhanced](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Call_of_Prypiat_Enhanced_Edition) and [SteamDB UFS](https://steamdb.info/app/2427430/ufs/) (app ID 2427430 and exact product spelling `Prypiat`). |

Original Steam locations are game-install data, not Documents:

| Игра | Путь | Проверка |
|---|---|---|
| Shadow of Chernobyl | `[Steam Library]/steamapps/common/STALKER Shadow of Chernobyl/_appdata_/savedgames` | [SteamDB UFS](https://steamdb.info/app/4500/ufs/) and [PCGamingWiki: Shadow](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Shadow_of_Chernobyl). |
| Clear Sky | `[Steam Library]/steamapps/common/STALKER Clear Sky/_appdata_/savedgames` | [SteamDB UFS](https://steamdb.info/app/20510/ufs/) and [PCGamingWiki: Clear Sky](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Clear_Sky). |
| Call of Pripyat | `[Steam Library]/steamapps/common/Stalker Call of Pripyat/_appdata_/savedgames` | [SteamDB UFS](https://steamdb.info/app/41700/ufs/) and [PCGamingWiki: Call of Pripyat](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Call_of_Pripyat). |

## Proton

PCGamingWiki's Steam Play note says that the prefix mirrors the Windows/Steam
paths and gives the Steam app ID. Поэтому статический путь раскрывается как:

```text
[Steam Library]/steamapps/compatdata/<app-id>/pfx/drive_c/users/steamuser/Documents/<X-Ray folder>/savedgames
[Steam Library]/steamapps/compatdata/<app-id>/pfx/drive_c/users/steamuser/Saved Games/<EE folder>/STEAM/savedgames
```

Для старых X-Ray сборок также проверяются `drive_c/users/Public/Documents` и
`drive_c/ProgramData/Documents`: некоторые retail-конфигурации используют
`%PUBLIC%`/`Public Documents`. Для S.T.A.L.K.E.R. 2 проверяется
`drive_c/users/steamuser/AppData/Local/Stalker2/Saved/...`.

App ID сверены по SteamDB: SoC `4500`, Clear Sky `20510`, Call of Pripyat
`41700`, S.T.A.L.K.E.R. 2 `1643320`, Enhanced `2427410`, `2427420`, `2427430`.
Источники: [SteamDB SoC](https://steamdb.info/app/4500/ufs/), [Clear Sky](https://steamdb.info/app/20510/ufs/),
[Call of Pripyat](https://steamdb.info/app/41700/ufs/), [S.T.A.L.K.E.R. 2](https://steamdb.info/app/1643320/ufs/),
[Enhanced bundle entries](https://steamdb.info/sub/1323391/). Реального Proton-prefix
на этой машине нет; наличие нужного дерева проверено synthetic fixture тестом.

## `fsgame.ltx` и локализация

X-Ray путь нельзя считать вечной константой. Публичный [iXray `fsgame.ltx`](https://github.com/ixray-team/ixray-1.0-stsoc/blob/default/fsgame.ltx)
содержит схему `true|false|root|relative`, `$app_data_root$` и
`$game_saves$ = true|false|$app_data_root$|savedgames\`. README публичного
[Stalker Xray tools](https://github.com/stalker-tools/tools) также прямо
перечисляет анализ `fsgame.ltx` и `.sav`. Реализация сначала уважает найденный
`fsgame.ltx`/`fsgame_soc.ltx` рядом с установленной игрой, затем использует
источниковые fallback-пути.

PCGamingWiki поясняет, что `Documents` заменяется на `My Documents` в Windows
XP. На современных локализованных системах имя Known Folder может быть иным;
поэтому discovery проверяет стандартные имена и существующие каталоги с
локализованными именами (`Документы`, `Документи`, `Documentos` и т.п.), но не
создаёт каталог и не делает безграничный рекурсивный поиск.

## Явные пробелы evidence

- Страницы [Clear Sky Enhanced](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Clear_Sky_Enhanced_Edition)
  и [Call of Prypiat Enhanced](https://www.pcgamingwiki.com/wiki/S.T.A.L.K.E.R.%3A_Call_of_Prypiat_Enhanced_Edition)
  подтверждают Steam/Proton path, но сейчас не дают отдельной точной строки
  для GOG save directory. Поэтому такие строки не объявлены подтверждёнными;
  код лишь возвращает уже существующий `.../<EE name>/gog/savedgames` и не
  создаёт его.
- Для retail/GOG/Proton не выполнялась загрузка сейва самой игрой и повторное
  сохранение. M03 доказывает discovery дерева путей, не совместимость
  контейнера: это отдельные M06–M09 gates.
- PCGamingWiki прямо указывает Steam Cloud paths под `userdata/<user-id>/<app-id>`;
  они относятся к синхронизируемому облачному storage, а не к локальному
  каталогу save slots, и в `save_directories()` не смешиваются с найденными
  локальными папками.

## Evidence commands

```text
PYTHON=.venv/bin/python -m pytest tests/test_platform_save_locations.py -q  -> 10 passed
PYTHON=.venv/bin/ruff check editor/platforms.py tests/test_platform_save_locations.py -> exit 0
PYTHON=.venv/bin/mypy editor/platforms.py -> exit 0
```

Тестовое дерево создаётся в `tmp_path`: проверены пустые Steam/GOG/Store roots,
другая Steam library из `libraryfolders.vdf`, malformed VDF с продолжением
поиска, manifests, локализованный Documents, Proton prefix, `fsgame.ltx`
override и отсутствие записи в filesystem.
