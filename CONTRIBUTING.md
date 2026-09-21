# Contributing and release

Run the local source gate before opening a change:

```bash
make check
make test
node --check web/app.js
git diff --check
```

Do not add personal saves, Steam session material, credentials, generated
release directories, or machine-specific paths. Parser and Steam Cloud changes
must retain the backup, source-hash, CRC/framing, atomic replacement and
fail-closed guards already covered by the tests.

## Release artifacts

The public tag workflow builds the Windows installer and portable ZIP, the
Linux portable archive, and the Debian package from the same commit. Linux
release packages are built inside an Ubuntu 22.04-compatible environment and
therefore advertise glibc 2.35 as their floor. A package built on a newer local
host honestly advertises that host's libc floor and is not a public release
candidate.

The Debian package is checked with `dpkg-deb`, AppStream validation and lintian.
Lintian `E:` and `W:` findings block a release; `I:` and `P:` findings are
reported but are explicitly non-fatal. The package contains a desktop entry,
icons, AppStream metainfo and a Debian copyright file.

The tag workflow requires all of these secrets before it deploys anything:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `APT_SIGNING_KEY` (ASCII-armored private key)
- `APT_SIGNING_KEY_ID`

It then prepares one stable directory, generates a signed `apt/` repository,
publishes package bytes and metadata to the R2 Worker, reads every public object
back, runs an isolated `apt update`/package-discovery check, and only then
creates or updates the GitHub Release. Direct `.deb` and portable downloads
remain release assets; the signed APT channel is an additional installation
path.

For local package-index work, prepare the stable files first and use an
ephemeral test key or an explicitly controlled local key:

```bash
make release-manifest ARTIFACT_DIR=release-input OUTPUT_DIR=release-output
make apt-repo VERSION=0.5.20 OUTPUT_DIR=release-output APT_SIGNING_KEY=<key-id>
```

Never commit the private key or the generated release directory.
