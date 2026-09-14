# Веб-сборка

Статическая страница: ни сборки, ни сервера. Запускает то же Python-ядро, что
и десктопное приложение, через Pyodide, и получает единственный нативный вызов
(распаковка Kraken) из `ooz-wasm`.

| Файл | Происхождение |
|---|---|
| `index.html`, `style.css`, `app.js`, `web_bridge.py` | пишутся руками |
| `pysrc.json` | **генерируется** из `save_format.py` и `editor/` командой `tools/build_web_bundle.py` |
| `theme.css` | **генерируется** из `ui/theme.py` командой `tools/export_theme.py` |

Генерируемые файлы коммитятся, чтобы GitHub Pages отдавал папку как есть, без
шага сборки. `make docs-check` падает, если они отстали от исходников.

```bash
make web-serve   # http://localhost:8765
```

Публикация: содержимое этой папки выложено в ветку `gh-pages` командой
`make web-publish`. GitHub Pages умеет отдавать только корень ветки или
`/docs`, поэтому папку `web/` из `main` он обслуживать не может.
Включается один раз: Settings → Pages → Deploy from a branch → `gh-pages`,
папка `/ (root)`. GitHub Actions не требуются.

## Куда выкладывать

| Вариант | Условие | Команда / действие |
|---|---|---|
| GitHub Pages | репозиторий должен быть **публичным** (на бесплатном тарифе Pages приватные репозитории не обслуживает) | `make web-publish`, затем Settings → Pages → `gh-pages` → `/ (root)` |
| Cloudflare Pages | репозиторий может остаться приватным; нужен один вход | `npx wrangler login`, затем `make web-deploy` |

`make web-deploy` отказывается публиковать, если в `web/` лежит `.sav`: эта же
папка служит корнем локального тестового сервера.
