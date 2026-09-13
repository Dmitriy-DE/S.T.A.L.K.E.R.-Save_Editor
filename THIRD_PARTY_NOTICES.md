# Third-party notices

## pyooz / ooz

This package includes `vendor/ooz.abi3.so`, extracted from the user-supplied `pyooz 0.0.8` Linux x86_64 wheel.

Project: https://github.com/zao/pyooz
PyPI: https://pypi.org/project/pyooz/
License: GNU GPL v3 or later.

The source for pyooz/ooz is available from the project above. This application is distributed under GPL-3.0 to keep redistribution compatible.

## SteamCloudFileManager

Project: https://github.com/Fldicoahkiin/SteamCloudFileManager
License: GPL-3.0.

SteamCloudFileManager is **not bundled**. The application invokes a separately installed/downloaded copy as a local helper using its `--steam-worker` IPC mode.

## Decoder source provenance

The upstream pyooz 0.0.8 source distribution and file hashes are retained in [third_party/pyooz](third_party/pyooz/README.md). The bundled Linux decoder matches the supplied wheel; a byte-identical source rebuild has not been performed. Windows/Qt packaging remains planned and must include its actual dependencies and notices.
