# Cloud diagnostics and OTA correction — 2026-09-21

## Confirmed source causes

- `remotecache.vdf` can list a real remote Steam object while its local
  `userdata/<user>/<app>/remote/...` byte copy is absent.
- The old read path kept only the filename. A cache metadata row therefore fell
  through to the native `ISteamRemoteStorage_FileExists`/`FileRead` path, even
  though Steam Web showed the same exact `Data/*.sav` object.
- Linux installed packages contain `BUILD_MANIFEST.json` under
  `/usr/lib/stalker2-save-editor`. The previous detection order classified that
  directory as generic portable before reaching the package check, so OTA could
  select the tarball and look for a portable updater.

## Implemented behavior

- `CloudFile.source` records native RemoteStorage, helper, web, local cache,
  cache metadata or unknown provenance.
- Cache local bytes are accepted only when their size matches metadata. A
  metadata-only read tries the web channel and otherwise stops with an explicit
  “metadata found, content unavailable” error; it never invokes native read.
- Logs are bounded to one 1 MiB file plus three rotating backups. Submission is
  opt-in, gzip-compressed, path/secret redacted, capped at 2 MiB by the Worker,
  and returns an opaque report id. R2 objects under `diagnostics/` are not
  publicly readable and are pruned after 30 days when a later report arrives.
- Verified Linux `.deb` updates use `pkexec apt-get install -y` when available,
  otherwise the desktop `xdg-open` handoff. Verified Windows installers launch
  separately; portable archives still use the external atomic updater.

## Local evidence

- `make test`: 572 passed.
- `make check`: Ruff, mypy, generated-file checks and bytecode compilation passed.
- Focused Steam Cloud, diagnostics, Worker-contract and updater/UI tests passed.
- No personal save, Steam session data, privileged package installation, live
  Steam upload, or in-game load/re-save was executed by these tests.

## External gates still required

The next release publication must separately verify the deployed Worker
`POST /diagnostics`, R2 retention/read policy, public `latest.json` and artifact
hashes, and a manual Linux/Windows update run. Steam Web/CDP availability and a
real Cloud upload remain user-owned runtime checks.
