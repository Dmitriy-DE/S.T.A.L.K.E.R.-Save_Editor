PYTHON ?= python3
SAVE ?=

.PHONY: check selftest run
check:
	$(PYTHON) -m py_compile app.py cli.py save_format.py steam_cloud.py tests/selftest_real.py

selftest: check
	@test -n "$(SAVE)" || (echo 'usage: make selftest SAVE=/path/to/file.sav' && exit 2)
	$(PYTHON) tests/selftest_real.py "$(SAVE)"

run:
	./run.sh
