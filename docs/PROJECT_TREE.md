# Структура после импорта

```text
app.py / cli.py / save_format.py / steam_cloud.py   runtime v0.3
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
```

Будущие editor/, ui/, packaging/ и CI перечислены в спецификации и появляются только при выполнении соответствующих задач.
