# Структура после импорта

```text
app.py / cli.py / save_format.py / steam_cloud.py   runtime v0.3
editor/                                               UI-free service, storage, cloud transaction and platform paths
ui/                                                   Tk-compatible Qt shell: inventory, changes, backups and Cloud tab
vendor/ooz.abi3.so                                 original Linux decoder
tests/selftest_real.py                             existing private-corpus selftest
releases/legacy/                                   original source bundles + SHA256SUMS
third_party/pyooz/                                 decoder source and provenance
README.md / AGENTS.md / CODEX_PROMPT.md             current entry points
docs/specs/                                       architecture and product requirements
docs/plans/                                       order and release gates
docs/tasks/                                       individual execution cards + issue links
docs/evidence/                                    reproducible result reports
docs/history/                                     historical project docs
.local/                                           ignored originals, saves and work logs
packaging/build.py                                stdlib-only standalone builder
packaging/editor.spec                             PyInstaller onedir spec (GUI + diagnostic)
packaging/gui_entry.py / diagnostic.py            packaged entry points
```

`packaging/` теперь содержит builder и spec B01. Локально на Linux x86_64
получены portable archive и `.deb`; Windows artifact и GitHub runner evidence
остаются обязательным внешним gate. P03 workflow запуски завершаются
`startup_failure` до jobs, поэтому этот локальный результат не объявляет
cross-platform beta готовой.
