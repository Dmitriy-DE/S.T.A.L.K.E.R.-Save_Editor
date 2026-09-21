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

## v0.5.18 publication evidence

- Merged source commit: `fe9529419122948a3527c325bb5b0f1bc807d5c3`; tag
  `v0.5.18` resolves to that commit.
- Hosted standalone run
  [35580270465](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/actions/runs/35580270465)
  passed the Linux and Windows package jobs, including Linux diagnostic smoke,
  Windows native smoke and Windows installer smoke. Its release job stopped at
  the existing fail-closed Cloudflare-secret check because the repository has
  no `CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID`; it did not alter artifacts.
- Windows artifacts came from that hosted run. Linux artifacts were built from
  the same merged source tree locally after the hosted Linux job passed; no
  privileged package installation was run locally.
- Worker deployment version: `b98aa8d7-a4a7-48bb-aac6-792533149fe3`.
  `tools/publish_release.py --prepared --publish-r2 --verify-r2` uploaded all
  six stable objects and read every public object back byte-for-byte.
- Live diagnostics smoke returned HTTP 201 with report id
  `da2e6a89-764f-401d-b404-90ca41e8f5b2`; `GET /diagnostics` returned 405 and
  the report path returned 404. The smoke payload contained no user data.
- [GitHub Release v0.5.18](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.18)
  contains the same six prepared files. Pages responds HTTP 200 and consumes
  the public manifest at `https://save-editor-downloads.save-editor.workers.dev/latest.json`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `SaveEditor-windows-x86_64.zip` | 62,295,909 | `614370553d10f61d8df1cd651e5f0daeab9a56c82caae41da8a3acd3a1e1fbee` |
| `SaveEditor-windows-x86_64-setup.exe` | 38,258,864 | `91977a0c3b9d5019a3e84ebdfd4068a1fccd4b0d50f7e8babb99491fe1945580` |
| `SaveEditor-linux-x86_64.tar.gz` | 83,478,437 | `0e8e5e9ee9bf73eb182c17ac77096ac55424286cb8d209eb1bad1f654685b0a4` |
| `stalker2-save-editor_amd64.deb` | 87,418,024 | `ade75b108d1f4fefff61fa9c41f3cdb3f7754eb082163fbf0494a75a9d11c7d2` |

## External gates still required

R2 cleanup is deployed as paginated, best-effort deletion of diagnostic objects
older than 30 days during later submissions; an old-object deletion was not
forced in production. Steam Web/CDP availability, a real Cloud `WriteFile`,
privileged package installation, and in-game load/re-save remain user-owned
runtime checks.
