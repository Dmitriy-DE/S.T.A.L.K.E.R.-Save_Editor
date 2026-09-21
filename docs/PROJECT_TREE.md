# Структура проекта

```text
cli.py / save_format.py / steam_cloud.py           parser, research CLI and Steam helper IPC
editor/                                            UI-free service, storage, cloud transaction and platform paths
editor/steam_vdf.py                                dependency-free Steam KeyValues reader
ui/                                                Qt interface: Zone theme, overview, inventory, changes, backups, Cloud
packaging/                                         PyInstaller builder for Linux tar.gz/.deb and Windows zip
web/                                               browser build: same core via Pyodide + ooz-wasm, generated bundle
tools/                                             maintenance scripts: task index, web bundle, theme export
vendor/ooz.abi3.so                                 Linux decoder binary
tests/selftest_real.py                             private-corpus selftest, never run in CI
third_party/pyooz/                                 decoder source and provenance
README.md / AGENTS.md                              entry points for contributors
docs/specs/                                       architecture and product requirements
docs/plans/                                       order and release gates
docs/tasks/                                       individual execution cards + issue links
docs/evidence/                                    reproducible result reports
docs/history/                                     historical project docs and handoffs
.local/                                           ignored originals, saves and work logs
packaging/build.py                                stdlib-only standalone builder
packaging/editor.spec                             PyInstaller onedir spec (GUI + diagnostic + native child)
packaging/gui_entry.py / diagnostic.py / native_entry.py  packaged entry points
```

`packaging/` теперь содержит builder и spec B01. Локально на Linux x86_64
получены portable archive и `.deb`; Windows artifact и GitHub runner evidence
остаются обязательным внешним gate. P03 workflow запуски завершаются
`startup_failure` до jobs, поэтому этот локальный результат не объявляет
cross-platform beta готовой.
