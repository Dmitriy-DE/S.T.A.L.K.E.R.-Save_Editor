# SteamCloudFileManager helper compatibility — P02

> Историческое evidence: helper transport удалён в SC-2 (PR #8). Ниже описан
> прежний offline/live probe, а не текущий путь Steam Cloud.

## Local runtime check — 2026-09-18

The project adapter was exercised with the extracted Linux `v1.3.5` helper and
the adjacent `libsteam_api.so`:

```text
SteamWorker.start()                    -> PONG
SteamWorker.connect(app_id=1643320)   -> OK
SteamWorker.list_files()               -> 0 files
WriteFile / SyncCloudFiles             -> not called
```

The AppImage copy could not start on this host because `libfuse.so.2` is not
installed. Discovery now prefers an extracted helper with its adjacent
Steamworks library and the worker adds that directory to `LD_LIBRARY_PATH` on
POSIX. This is a runtime convenience, not a bundled binary: the helper remains
an external dependency and its license/redistribution boundary is unchanged.

`Connect=OK` proves the local helper/Steamworks session handshake only. The
empty `GetFiles` result means no cloud save slot was visible in that session;
it does not prove that the account has no saves, and no upload was attempted.

Проверка зафиксирована 2026-09-13. В качестве reference взят upstream tag
`v1.3.5`, peeled commit `1388e292ec502257545bc0e12927a50d2141d8bf`.

## Проверенный контракт исходника

В [`src/steam_worker.rs` на v1.3.5](https://github.com/Fldicoahkiin/SteamCloudFileManager/blob/v1.3.5/src/steam_worker.rs)
описан line-delimited JSON worker, запускаемый с аргументом
`--steam-worker`. Request enum содержит `Ping`, `Connect { app_id }`,
`GetFiles`, `ReadFile { filename }`, `WriteFile { filename, data }`,
`SyncCloudFiles` и `Exit`; responses содержат `Pong`, `Connected`, `Files`,
`FileData`, `Ok` и `Error`. Это совпадает с полями, которые отправляет и
разбирает `steam_cloud.py`.

Версия helper закреплена как reference для P02/S06, но его binary не входит в
этот репозиторий. Сверены source protocol и release availability; SHA
конкретного скачанного Windows/Linux asset не записывается, потому что asset
не скачивался в текущую среду.

## Что покрывает код

- `editor.platforms.discover_helper()` ищет явный путь из
  `STALKER2_STEAM_HELPER`, затем PATH и ограниченный набор Downloads/
  Applications/Program Files каталогов.
- Linux возвращает только файл с execute bit; Windows не зависит от POSIX
  execute bits и выбирает `.exe`. Наличие соседних DLL не требует изменения
  пути запуска: Windows ищет DLL рядом с executable.
- `SteamWorker` передаёт `[helper, "--steam-worker"]` в
  `subprocess.Popen` с `shell=False`; `.exe` никогда не chmod-ится.
- Пустой/missing helper оставляет local-only режим работоспособным; Steam
  connect остаётся отдельным manual gate.

## Evidence

```text
python3 -m pytest tests/test_platforms.py -v        -> 10 passed
python3 -m pytest tests/test_worker_lifecycle.py -q  -> 7 passed
make test                                           -> 56 passed
make check                                          -> exit 0
bash -n run.sh                                      -> exit 0
git ls-remote ... refs/tags/v1.3.5^{}               -> 1388e292ec502257545bc0e12927a50d2141d8bf
```

Текущая машина Linux x86_64. `run.bat` проверен как исходник launcher-а, но не
исполнялся на Windows; fake helper проверяет Ping/worker lifecycle offline,
а реальный helper, Steam client, cloud sync и GFN не запускались.
