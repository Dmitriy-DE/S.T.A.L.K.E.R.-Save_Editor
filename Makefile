PYTHON ?= python3
SAVE ?=

.PHONY: check lint typecheck test selftest run package-plan package
check: lint typecheck
	$(PYTHON) -m py_compile app.py cli.py save_format.py steam_cloud.py tests/selftest_real.py

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest tests

selftest: check
	@test -n "$(SAVE)" || (echo 'usage: make selftest SAVE=/path/to/file.sav' && exit 2)
	$(PYTHON) tests/selftest_real.py "$(SAVE)"

run:
	./run.sh

package-plan:
	$(PYTHON) packaging/build.py --plan

package:
	$(PYTHON) packaging/build.py --target auto --output-dir dist
