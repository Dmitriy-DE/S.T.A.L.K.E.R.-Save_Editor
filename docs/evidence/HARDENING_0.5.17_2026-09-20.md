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

Hosted source matrix [35538975049](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35538975049)
passed on Ubuntu 3.11/3.12 and Windows 3.11/3.12. Hosted standalone build
[35539090000](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35539090000)
passed on Linux and Windows, including Windows installer smoke. The final
release job correctly stopped before publishing because the GitHub repository
has no `CLOUDFLARE_API_TOKEN` or `CLOUDFLARE_ACCOUNT_ID` secrets. After the
package jobs passed, the exact prepared bytes were published through the local
authorized Wrangler/`gh` session.

Final public artifacts from source commit
`639557bc656e40681b63e4edf848c12fce7068e9`:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `SaveEditor-windows-x86_64.zip` | 62,019,536 | `e62ac213394b817250ede47eec67ca48179189c612f1c7824778e57e1eb31e8b` |
| `SaveEditor-windows-x86_64-setup.exe` | 38,195,465 | `6554147ac2299d2a11edf6d3ac36d118bbe5d8b9015047a86faf46d17aada64b` |
| `SaveEditor-linux-x86_64.tar.gz` | 89,790,188 | `ea1547e591ff78eafc8629c00acaddcae489b7538ea89fdab116c25a5d4c8f4a` |
| `stalker2-save-editor_amd64.deb` | 93,125,120 | `863b7d0c3a96a3def35b41ef7fa2ff7b2a1f9831eedf6a518b7bf36b9378e987` |

Worker version `e9b23133-910d-4d73-9ab7-8933cbac041a` served all six R2
objects. Independent public read-back verified every advertised artifact size
and SHA-256, and the GitHub Release
[v0.5.17](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.17)
was downloaded and verified against the same manifest. Pages deployment
[`7e3cd3e8`](https://7e3cd3e8.stalker-save-editor.pages.dev/) and the canonical
site returned HTTP 200 with separate Windows installer/portable links.
