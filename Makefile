PYTHON ?= python3
SAVE ?=

.PHONY: check lint typecheck docs docs-check web web-serve web-publish web-deploy test selftest run package-plan package
check: lint typecheck docs-check
	$(PYTHON) -m py_compile cli.py save_format.py steam_cloud.py tests/selftest_real.py

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy

docs:
	$(PYTHON) tools/render_task_index.py

docs-check:
	$(PYTHON) tools/render_task_index.py --check
	$(PYTHON) tools/build_web_bundle.py --check
	$(PYTHON) tools/export_theme.py --check

web:
	$(PYTHON) tools/build_web_bundle.py
	$(PYTHON) tools/export_theme.py

web-serve: web
	@echo "http://localhost:8765"
	$(PYTHON) -m http.server 8765 --directory web

# Publish web/ to Cloudflare Pages (stalker2-save-editor.pages.dev).  Requires
# `npx wrangler login` once.  The guards exist because this directory doubles as
# the local test server root: neither a save nor Python bytecode may ship.
web-deploy: web
	@! find web -name '*.sav' -o -name '*.bak' | grep -q . || \
		(echo "web/ contains a save file; remove it before deploying" && exit 2)
	@rm -rf web/__pycache__
	npx --yes wrangler@4 pages deploy web \
		--project-name=stalker2-save-editor --branch=main --commit-dirty=true

# Publish web/ to the gh-pages branch, which GitHub Pages serves at its root.
# Pages can only deploy a branch's root or /docs, never an arbitrary folder,
# so the site cannot be served from web/ on main directly.
web-publish: web
	@test -z "$$(git status --porcelain)" || (echo "commit changes first" && exit 2)
	git subtree push --prefix web origin gh-pages

test:
	$(PYTHON) -m pytest tests

selftest: check
	@test -n "$(SAVE)" || (echo 'usage: make selftest SAVE=/path/to/file.sav' && exit 2)
	$(PYTHON) tests/selftest_real.py "$(SAVE)"

run:
	$(PYTHON) -m ui

package-plan:
	$(PYTHON) packaging/build.py --plan

package:
	$(PYTHON) packaging/build.py --target auto --output-dir dist
