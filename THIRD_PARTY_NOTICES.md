# Third-party notices

## pyooz / ooz

The source tree includes `vendor/ooz.abi3.so`, extracted from the user-supplied
`pyooz 0.0.8` Linux x86_64 wheel. Runtime installations use the matching
platform `pyooz==0.0.8` wheel; the loader keeps the Linux binary as a legacy
fallback and never presents it as a Windows dependency.

Project: https://github.com/zao/pyooz
PyPI: https://pypi.org/project/pyooz/
License: GNU GPL v3 or later.

The source for pyooz/ooz is available from the project above. This application is distributed under GPL-3.0 to keep redistribution compatible.

## SteamCloudFileManager

Project: https://github.com/Fldicoahkiin/SteamCloudFileManager
License: GPL-3.0.

SteamCloudFileManager is **not bundled**. The application invokes a separately installed/downloaded copy as a local helper using its `--steam-worker` IPC mode.

## PySide6 / Qt

The standalone desktop bundle includes `PySide6==6.11.2` and the Qt runtime
plugins selected by PyInstaller. PySide6 is distributed by Qt Group under the
LGPL/GPL and commercial licensing options; the applicable license texts and
notices shipped by the wheel are retained in the generated bundle. See the
[PySide6 licensing documentation](https://doc.qt.io/qtforpython-6/licenses.html)
before redistributing a binary package.

## PyInstaller

Builds use `PyInstaller==6.22.3`. PyInstaller is a build-time tool and is not
required by the source editor at runtime. Its bootloader and license notice
are included in the generated artifact according to the PyInstaller license.
The pinned build input is recorded in `requirements-build.txt` and
`BUILD_MANIFEST.json`.

## Decoder source provenance

The upstream pyooz 0.0.8 source distribution and file hashes are retained in [third_party/pyooz](third_party/pyooz/README.md). The bundled Linux decoder matches the supplied wheel; a byte-identical source rebuild has not been performed. The Windows wheel is provenance-checked but is not bundled in this source checkout; packaged builds must include its actual dependency and notices.

## ooz-wasm (веб-версия)

Веб-сборка загружает `ooz-wasm` 2.0.0 с CDN — WebAssembly-биндинг к
[powzix/ooz](https://github.com/powzix/ooz), лицензия GPL-3.0-or-later,
совместимая с лицензией проекта. Он выполняет ровно одну функцию: распаковку
Kraken-потока. В десктопные пакеты не вкладывается.

## Pyodide (веб-версия)

Веб-сборка загружает Pyodide 0.28.3 с CDN (Mozilla Public License 2.0) — это
CPython, собранный в WebAssembly. В десктопные пакеты не вкладывается.
