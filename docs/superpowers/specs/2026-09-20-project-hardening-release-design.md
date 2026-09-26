# Project Hardening and Release Design

## Purpose

Close the concrete defects found in the 2026-09-20 repository audit and ship
one coherent release.  The release must be honest about unsupported save
formats and equipment fields, keep every existing backup/integrity guard, and
make CI, Steam Cloud, updates, web startup, publication, and repository hygiene
agree with the behaviour users actually receive.

## Success criteria

- Linux and Windows static analysis and tests pass on Python 3.11 and 3.12.
- Release packaging runs the same source gate as normal CI before producing
  artifacts.
- A Steam Cloud transport advertises whether it can write.  Read-only web/cache
  fallbacks never enable upload and never report a pre-write refusal as an
  uncertain remote write.
- A write that may have reached Steam remains `uncertain` and is never retried.
- Update redirects are validated before a redirected request is sent.
- A failed cleanup after a successful portable swap cannot roll the new
  installation back.
- A tag cannot publish a GitHub release while Worker/R2 publication is skipped.
- The browser starts independent network work concurrently and does not block
  file selection on catalog installation; analysis waits for the catalog.
- Proven dead code and unused imports are removed without changing supported
  save-format behaviour.
- Public documentation, version metadata, GitHub assets, R2 metadata, and Pages
  describe the same release.

## Safety boundary

This work does not invent save offsets, serializers, item identifiers, or game
acceptance evidence.  Issues #95, #96, and #97 require controlled save pairs or
in-game validation and remain open until that evidence exists.  Existing
unknown S.T.A.L.K.E.R. 2 equipment, Enhanced Edition saves, and unvalidated
X-Ray mutations remain fail-closed.  "Perfect" in this project means truthful
capabilities and recoverable writes, not guessed mutation support.

No automated test may write to a real Steam Cloud slot.  Cloud tests use fake
transports and the existing live-session guard.  Release read-back may access
only the project's public Worker, R2 objects, GitHub release assets, and Pages.

## Cloud write capability

Create a small shared capability module with two public contracts:

```python
@dataclass(frozen=True)
class CloudWriteCapability:
    writable: bool
    reason: str

class CloudWriteNotAttemptedError(RuntimeError):
    pass
```

`cloud_write_capability(transport)` reads the advertised capability and fails
closed when a third-party transport does not advertise one.  Production
transports expose these states:

- Native RemoteStorage backend after a successful native listing: writable;
- Steam web/CDP fallback: read-only with a web-specific reason;
- local Steam cache fallback: read-only with a cache-specific reason.

The UI uses this contract for button state and explanatory text.  The upload
transaction checks it before fresh read, backup creation, or recovery creation.
If a transport raises `CloudWriteNotAttemptedError` after preflight, the result
is a normal `CloudTransactionError`; all other exceptions after invoking
`write_file` remain `uncertain`.

## Update safety

`UpdateClient` uses an opener whose redirect handler validates every target
against the same scheme/host/no-credentials/no-query/no-fragment policy as the
initial URL.  A disallowed redirect is rejected before the target server is
contacted.

Portable replacement has a commit point: after the staged tree replaces the
current tree and the new executable is launched, backup deletion is best-effort
cleanup.  Cleanup failure may leave a backup directory, but it cannot remove
the working new installation or trigger rollback.

## CI and release publication

The Windows ctypes lookup must type-check on both POSIX and Windows mypy
platforms without platform-dependent `type: ignore` comments.  The normal
four-job matrix remains the source compatibility gate.

Both Linux and Windows package jobs run ruff, mypy, generated-file checks, and
pytest before building.  The publish job rejects missing Cloudflare credentials
before deployment or GitHub release creation.  It then deploys Worker, prepares
stable files once, uploads/verifies R2, and publishes those exact files to the
GitHub release.  Missing credentials are a failed release, never a warning-only
split channel.

## Browser startup

Move network/bootstrap primitives into a small ES module that can be exercised
under Node.  Decoder import, Pyodide module import, Python source bundle fetch,
and bridge fetch begin together.  Catalog fetch begins after the bridge is
installed and resolves in the background.  The file picker becomes available
when the core is ready; `openFile` awaits the catalog promise before analysis.
Catalog failure remains visible and blocks analysis rather than producing an
unnamed or partially initialised editor.

## Maintainability and cleanup

Remove imports and definitions that have no call sites, exports, tests, or
documented compatibility role.  Public-looking research helpers are removed
only after repository-wide reference and export checks.  Generated browser
bundles are rebuilt from the resulting source.

Keep the current parser boundaries intact.  Large parser functions are not
split merely to improve a metric.  Extract only update/bootstrap/cloud logic
where the new contracts create a real testable boundary.

Stale remote branches are reviewed by unique commit before deletion.  The
independent `gh-pages` history is retained.  Local Git maintenance uses normal
retention-aware garbage collection; no force deletion of recoverable history.

## Verification and release evidence

Each behavioural change follows RED -> GREEN.  Final verification includes:

- ruff, Linux mypy, Windows-platform mypy, generated docs/web/theme checks;
- the complete pytest suite;
- Node bootstrap tests and JavaScript syntax checking;
- Linux portable and Debian builds plus packaged diagnostic smoke;
- hosted Linux/Windows matrix and tag packaging jobs;
- public GitHub/Worker manifest byte equality and public artifact read-back;
- Pages deployment status and a clean tracked worktree.

External in-game validation and real Steam Cloud writes are reported as
external gates, never inferred from structural tests.
