<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="S.T.A.L.K.E.R. Save Editor"/>
</p>

<p align="center">
  <a href="https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/latest"><img src="https://img.shields.io/github/v/release/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor?style=flat-square&label=release&color=C69A3E" alt="Latest release"/></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/Windows-x64-0078D4?style=flat-square&logo=windows&logoColor=white" alt="Windows x64"/>
  <img src="https://img.shields.io/badge/Linux-x86__64-FCC624?style=flat-square&logo=linux&logoColor=000" alt="Linux x86_64"/>
  <img src="https://img.shields.io/badge/license-GPL--3.0-7E8F3E?style=flat-square" alt="GPL-3.0"/>
</p>

<p align="center">
  <a href="https://stalker-save-editor.pages.dev"><b>Open in browser</b></a>
  ·
  <a href="https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/latest"><b>Download desktop</b></a>
  ·
  <a href="https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/issues"><b>Report an issue</b></a>
</p>

# S.T.A.L.K.E.R. Save Editor

A cross-platform save editor for the official PC releases of **S.T.A.L.K.E.R. 2** and the original **Shadow of Chernobyl / Clear Sky / Call of Pripyat** trilogy.

The project uses **one Python editing core** across the Qt desktop app, CLI and browser build. Local files are analysed offline; unsupported structures stay read-only instead of being guessed.

> **Safety first:** edits are staged and verified before saving. The main desktop
> **Сохранить** action asks once, creates a verified backup, and atomically updates
> the opened local slot; Steam Cloud writes remain explicit and guarded by
> backup/hash verification.

The current release line is `0.5.19`. A release is published only from a clean
tagged commit after the Linux and Windows packaged gates pass.

<p align="center">
  <img src="./assets/readme/workbench.svg" width="100%" alt="S.T.A.L.K.E.R. Save Editor workbench"/>
</p>

<p align="center"><sub>Illustrative values; the layout and controls are reconstructed from the actual desktop/browser UI.</sub></p>

## What it does

- discovers local saves for supported official PC releases;
- detects the game/release from file contents instead of trusting the filename;
- reads money, inventory and technical container metadata;
- edits only capabilities proven for the detected format;
- stages changes before writing;
- verifies CRC / Kraken framing / parser round-trip where applicable;
- exports a new local copy;
- provides a Qt desktop app, CLI and browser build over the same core;
- supports S.T.A.L.K.E.R. 2 Steam Cloud from the desktop app;
- packages standalone Windows and Linux builds — **Python is not required for end users**.

## Game support

| Game | Status | Editing surface |
|---|---|---|
| **S.T.A.L.K.E.R. 2: Heart of Chornobyl** | Supported | money, confirmed stack edits, save-local inventory names; experimental condition editing for confirmed equipped armour; desktop Steam Cloud |
| **Shadow of Chernobyl — Original** | Supported | X-Ray inventory, money, confirmed stacks, catalogue-backed item operations and confirmed equipment fields |
| **Clear Sky — Original** | Supported | X-Ray inventory, money, confirmed stacks, catalogue-backed item operations; experimental equipment/upgrades where the exact format anchor is proven |
| **Call of Pripyat — Original** | Supported | X-Ray inventory, money, confirmed stacks, catalogue-backed item operations; helmet/equipment/upgrades where the exact format anchor is proven |
| **Enhanced Editions** | Not yet supported | release/path profiles exist, but parsing and editing stay disabled until format evidence is available |
| **Mods / unknown save formats** | Out of scope | fail closed |

### S.T.A.L.K.E.R. 2 boundaries

The project intentionally does **not** pretend that every visible catalogue entry can already be reconstructed inside a save.

Still read-only / research-gated in S2:

- arbitrary item creation from SID;
- general weapon condition editing;
- weapon/equipment upgrade mutation without a proven serializer path;
- unknown GVAS inventory structures;
- unsupported Enhanced Edition containers.

## Download

The latest release ships four end-user packages.

| Platform | Package |
|---|---|
| Windows | [Installer (.exe)](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/latest/download/SaveEditor-windows-x86_64-setup.exe) |
| Windows | [Portable (.zip)](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/latest/download/SaveEditor-windows-x86_64.zip) |
| Linux / Debian / Ubuntu | [.deb package](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/latest/download/stalker2-save-editor_amd64.deb) |
| Linux | [Portable (.tar.gz)](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/latest/download/SaveEditor-linux-x86_64.tar.gz) |
| Browser | [stalker-save-editor.pages.dev](https://stalker-save-editor.pages.dev) |

The next tagged release also publishes a signed APT channel through the same
R2 download Worker. After importing its public key, Debian/Ubuntu users can
install and receive later package versions with the normal package manager:

```bash
curl -fsSL https://save-editor-downloads.save-editor.workers.dev/apt/repository-key.asc \
  | gpg --dearmor | sudo tee /usr/share/keyrings/stalker2-save-editor.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/stalker2-save-editor.gpg] https://save-editor-downloads.save-editor.workers.dev/apt stable main" \
  | sudo tee /etc/apt/sources.list.d/stalker2-save-editor.list >/dev/null
sudo apt update
sudo apt install stalker2-save-editor
```

The current `v0.5.19` assets remain available as direct downloads; the signed
APT channel is published by the next tag only after its key, package, R2
read-back and disposable `apt update` gates pass.

Checksums are published with each GitHub release.
Current stable release: [v0.5.19](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases/tag/v0.5.19).

## Desktop workflow

```text
Zone library
    ↓
choose / import save
    ↓
content-based format detection
    ↓
inspect inventory + metadata
    ↓
stage supported edits
    ↓
click «Сохранить» and confirm once
    ↓
internal preview + CRC/SHA verification
    ↓
verified backup + atomic save
```

The preview, backup and write stages are internal to the normal desktop flow;
the technical change journal remains available for diagnostics, but it is not a
required extra tab or action. Steam Cloud keeps its separate explicit upload
confirmation and fail-closed transaction because a remote write can be
uncertain after Steam accepts it.

The desktop app exposes a release-aware Steam Cloud flow for S.T.A.L.K.E.R. 2,
the original trilogy and separate Enhanced Edition profiles. Each profile carries
its Steam app ID and remote save root into native, helper, cache and CDP paths;
the UI reports which backend answered. Native calls use bounded subprocesses so a
stuck Steam call cannot freeze the Qt UI indefinitely. Upload remains explicit,
backup/hash guarded and reports verified versus uncertain outcomes. Only a native
or helper backend that explicitly advertises write support can enable upload;
Steam web/CDP and local-cache discovery remain read-only and explain why. A
preflight refusal is a definite no-write result. An exception after `WriteFile`
may have reached Steam, is reported as uncertain, and is never retried
automatically.

Every cloud row also shows its provenance: Steam RemoteStorage, helper, Steam
Cloud web, local Steam cache, or cache metadata. A cache metadata row is a
remote listing without downloaded bytes; the app never sends it to native
`FileRead` by mistake. The **Отправить логи** button collects only bounded,
rotated technical logs, redacts local home paths and secret-like values, and
returns an opaque report id. Save bytes are not included.

## Updates and standalone packages

Each GitHub release publishes separate Windows installer and portable ZIP files,
Linux portable `tar.gz`, Debian `.deb`, `latest.json` and `SHA256SUMS`. The
signed APT channel mirrors the Debian package and its repository metadata:

- the installer creates the normal Windows installation and shortcut;
- **Windows portable** ZIP and **Linux portable** tar.gz require neither Python
  nor installation;
- desktop checks `latest.json` in the background and has a manual
  **автообновление** action;
- portable updates verify size and SHA-256, then replace files only after the
  application exits; Windows installer and Linux `.deb` updates launch the
  verified system handoff and require explicit confirmation/privilege approval.
- An installed Linux `.deb` is detected separately from Linux portable, so its
  update check selects the `.deb` artifact instead of downloading a tarball.
- APT installations update through `apt update`/`apt upgrade`; direct `.deb`
  downloads and Linux portable remain independent fallback installation paths.

The manifest and binaries are also mirrored to the public Cloudflare R2 download
worker. Redirect destinations are checked before the updater contacts them.
Invalid manifests, unexpected hosts, network failures or hash mismatches leave
the current installation untouched; a failed cleanup after a successful portable
swap leaves the recoverable backup in place without rolling the new version back.

Tag publication prepares the stable files once, uploads and reads those exact
bytes back through the public Worker, and only then attaches the same directory
to GitHub Release. Missing Cloudflare credentials fail the release job instead
of silently publishing a split GitHub-only release.

Old v0.5.14 installations do not contain the corrected package detection and
installer handoff. Install the current `.deb` once from the release page; later
checks can hand the verified package to `pkexec apt-get` (or the desktop
installer fallback) automatically.

Release preparation and R2 read-back use the repository tools:

```bash
make release-manifest ARTIFACT_DIR=release-input OUTPUT_DIR=release-output
make apt-repo VERSION=0.5.19 OUTPUT_DIR=release-output APT_SIGNING_KEY=<key-id>
make r2-publish ARTIFACT_DIR=release-input OUTPUT_DIR=release-output
```

## Browser build

The browser version runs the same Python core through **Pyodide/WebAssembly**.

- the save stays in the browser tab;
- there is no application backend receiving the file;
- supported local edits can be downloaded as a new copy;
- decoder, Pyodide and shared core resources load concurrently; the catalogue
  continues in the background, while analysis waits for it before exposing data;
- Steam Cloud is desktop-only.

Run it locally:

```bash
make web-serve
# http://localhost:8765
```

## Architecture

```text
                    ┌──────────────────────┐
                    │   shared Python core │
                    │ parser / editor /    │
                    │ preview / verify     │
                    └──────────┬───────────┘
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
      Qt desktop app          CLI        Browser / Pyodide
             │                                   │
             ▼                                   ▼
      Steam Cloud / local                    local files
```

Important boundaries:

- **UI does not own save mutation logic** — it goes through the shared editor service.
- **Unknown fields remain opaque/read-only.**
- **Content detection wins over path assumptions.**
- **Round-trip correctness is not treated as proof of in-game semantic acceptance.**
- **Live Steam writes and game load/re-save checks are kept separate from automated CI.**
- **S2 weapon/helmet condition, arbitrary equipment creation/upgrades and Enhanced
  Edition parsing stay read-only until controlled differential and in-game evidence exists.**

## Run from source

Requires Python 3.11+.

```bash
git clone https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor.git
cd S.T.A.L.K.E.R.-Save_Editor

python3 -m pip install -r requirements.txt
python3 -m ui
```

Windows:

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m ui
```

CLI:

```bash
python3 cli.py --help
```

The CLI supports the same bounded edit surface where the selected format is
confirmed: money, stacks, durability, upgrades and placement. Unsupported S2
equipment structures and Enhanced Edition bytes fail closed instead of being
written through a guessed serializer.

Developer checks:

```bash
python3 -m pip install -r requirements-dev.txt
make check
```

CI covers source tests plus packaged diagnostics for Linux and Windows. Release builds also produce the Windows installer, portable archives, Debian package, manifest and SHA-256 checksums.

## Project status

The current stable release is shown in the badge above. Release history and binaries are available on the [Releases](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/releases) page.

The detailed engineering/evidence log remains in [docs/STATUS.md](docs/STATUS.md). Format research and validation evidence live under [docs/evidence/](docs/evidence/).

The public Issues board is for **bugs, user-facing features and roadmap items**. Internal research notes and implementation cards belong in the repository documentation, not as dozens of open user-facing tickets.

## Roadmap

- [S.T.A.L.K.E.R. 2: expand equipment editing beyond confirmed armour anchors](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/issues/95)
- [Enhanced Editions: add safe format detection and parser support](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/issues/96)
- [Validate experimental X-Ray equipment mutations in game](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/issues/97)
- [Steam Cloud: broaden support and improve runtime diagnostics](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/issues/98)
- [UX: simplify save flow without weakening backup and verification](https://github.com/Dmitriy-DE/S.T.A.L.K.E.R.-Save_Editor/issues/99)
## Contributing

Bug reports and focused feature requests are welcome.

Before opening a bug, include:

- game + edition;
- editor version;
- desktop / browser / CLI;
- OS;
- what you expected;
- what happened;
- whether the original save still loads.

Do **not** attach personal save files publicly unless you are comfortable publishing their contents. A minimal synthetic/reproducible sample is preferred.

## License

GNU GPL v3. See [LICENSE](LICENSE).

S.T.A.L.K.E.R. and related names/assets belong to their respective owners. This project is an independent community tool and is not affiliated with GSC Game World.
