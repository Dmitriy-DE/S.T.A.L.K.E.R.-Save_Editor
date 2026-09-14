PYTHON ?= python3
SAVE ?=

.PHONY: check lint typecheck docs docs-check web web-serve test selftest run package-plan package
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
