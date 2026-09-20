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
After commit `01ec5f14dbbe`, the clean-tree `make package` gate passed and
produced:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `SaveEditor-linux-x86_64-v0.5.17.tar.gz` | 83,143,696 | `67c6f7e855861da8fdbe93b331d0c902883fe06b09c146c2ba46766950abf7ea` |
| `stalker2-save-editor_0.5.17_amd64.deb` | 87,287,470 | `b8151f91b22947646a12b028d7e6d3388cff672490f3d13eaeb59099888d55a4` |

`sha256sum -c` passed. The extracted portable diagnostic reported Linux
x86_64, Qt 6.11.2 and a loaded bundled `ooz.abi3.so`; its build manifest was
version 0.5.17 with `source_dirty=false`. The packaged native child completed a
read-only list operation. No `WriteFile`, package installation or game
load/re-save was performed.

Hosted Linux/Windows, Worker/R2/GitHub and Pages read-back remain pending until
the verified commit is integrated and tagged. Hosted artifacts will be rebuilt
from that final tag and therefore have their own published size/SHA evidence.
