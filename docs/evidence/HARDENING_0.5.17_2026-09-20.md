# v0.5.17 hardening evidence — 2026-09-20

## Scope

- cross-platform source gates before packaging;
- explicit Steam Cloud write capability and fail-closed read-only fallbacks;
- redirect-safe updater and post-commit backup cleanup;
- one prepared byte set for Worker/R2 and GitHub Release;
- concurrent browser bootstrap with deferred, mandatory catalogue installation;
- repository-backed dead-code cleanup.

## Safety boundary

Automated tests use fake Cloud transports and local HTTP servers. They do not
write a real Steam slot or claim in-game acceptance. S.T.A.L.K.E.R. 2
weapon/helmet condition, arbitrary item creation/upgrades, Enhanced Edition
parsing and experimental X-Ray mutations still require controlled differential
fixtures and game load/re-save evidence.

## Verification state

Local source gate passed:

- `make check`: Ruff, native mypy, generated docs/web/theme and `py_compile`;
- `python -m mypy --platform win32`: 81 source files;
- `python -m pytest tests -q`: **560 passed**;
- `node --test tests/js/web-bootstrap.test.mjs`: **2 passed**;
- `node --check web/bootstrap.js` and `node --check web/app.js`.

The packaging command correctly refused the dirty documentation/version tree.
The clean-tree Linux package build and packaged diagnostics are the next local
gate. Hosted Linux/Windows, Worker/R2/GitHub and Pages read-back remain pending
until the verified commit is integrated and tagged.
