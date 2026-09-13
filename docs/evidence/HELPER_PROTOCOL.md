# SteamCloudFileManager worker protocol — S06

Reference проверен 2026-09-13 по tag `v1.3.5`, peeled commit
`1388e292ec502257545bc0e12927a50d2141d8bf`:

- [`src/steam_worker.rs`](https://github.com/Fldicoahkiin/SteamCloudFileManager/blob/v1.3.5/src/steam_worker.rs)
  defines line-delimited JSON request/response enums;
- `Ping` → `Pong` is the offline readiness handshake;
- `Connect { app_id }` → `Connected { app_id }` starts the Steamworks session;
- `GetFiles` → `Files { files }`, `ReadFile { filename }` →
  `FileData { data }`, `WriteFile { filename, data }` → `Ok`/`Error`;
- `SyncCloudFiles` → `Ok`/`Error`, `Exit` terminates the worker.

The source's `WorkerCloudFile.is_persisted` is populated from the Steamworks
`SteamFile::is_persisted()` handle state. It is a client-side persistence flag;
the helper source also states that sync is asynchronous. Therefore S06 treats
`persisted=true` as one required signal and still performs a second `ReadFile`
SHA check. Neither signal alone is a proof that a remote server snapshot is
immutable or that a game/GFN session has reloaded it.

## Transaction contract

`editor.transactions.upload_cloud(worker, prepared, backup_dir)` uses the exact
cloud locator stored in `PreparedEdit.plan.source.locator`:

```text
fresh ReadFile + expected source SHA
  → exclusive ORIGINAL backup
  → exclusive EDITED recovery
  → one WriteFile
  → SyncCloudFiles
  → wait persisted=true
  → one ReadFile read-back + output SHA
```

Any failure before `WriteFile` raises `CloudTransactionError` and leaves
`write_calls==0` in the fake contract tests. Any failure after `WriteFile`
returns `CloudReceipt(status="uncertain", ...)` with both recovery paths and
no automatic retry. Full success returns `status="verified"`; the receipt
does not claim game or GFN semantic acceptance.

Live helper/Steam calls are intentionally absent from this evidence. Fake
transport coverage is the deterministic gate; real connect/sync requires a
separate disposable-slot manual run.
