PYTHON ?= python3
SAVE ?=
VERSION ?= $(shell sed -n '1p' VERSION)
ARTIFACT_DIR ?= release-input
OUTPUT_DIR ?= release-output
APT_SIGNING_KEY ?=
APT_GPG_HOME ?= /tmp/save-editor-apt-gnupg
CORPUS_OUT ?= $(HOME)/.local/share/Stalker2SaveEditor/corpus-lab

.PHONY: check lint typecheck docs docs-check web web-serve web-publish web-deploy test selftest run package-plan package release-manifest apt-repo r2-publish corpus-lab
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

# Publish web/ to Cloudflare Pages (stalker-save-editor.pages.dev).  Requires
# `npx wrangler login` once.  The guards exist because this directory doubles as
# the local test server root: neither a save nor Python bytecode may ship.
web-deploy: web
	@! find web -name '*.sav' -o -name '*.bak' | grep -q . || \
		(echo "web/ contains a save file; remove it before deploying" && exit 2)
	@rm -rf web/__pycache__
	npx --yes wrangler@4 pages deploy web \
		--project-name=stalker-save-editor --branch=main --commit-dirty=true

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

release-manifest:
	$(PYTHON) tools/publish_release.py --artifacts $(ARTIFACT_DIR) --version $(VERSION) --commit $$(git rev-parse HEAD) --output $(OUTPUT_DIR)

apt-repo:
	@test -n "$(APT_SIGNING_KEY)" || (echo 'usage: make apt-repo APT_SIGNING_KEY=<key-id>' && exit 2)
	$(PYTHON) tools/build_apt_repo.py --package $(OUTPUT_DIR)/stalker2-save-editor_$(VERSION)_amd64.deb --output $(OUTPUT_DIR)/apt --signing-key $(APT_SIGNING_KEY) --gpg-home $(APT_GPG_HOME)

r2-publish:
	$(PYTHON) tools/publish_release.py --artifacts $(ARTIFACT_DIR) --version $(VERSION) --commit $$(git rev-parse HEAD) --output $(OUTPUT_DIR) --publish-r2 --verify-r2

corpus-lab:
	@test -n "$(ROOTS)" || (echo 'usage: make corpus-lab ROOTS="<save folder> [another folder]"' && exit 2)
	$(PYTHON) tools/corpus_lab.py --roots $(ROOTS) --out "$(CORPUS_OUT)"
