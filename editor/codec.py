"""Platform-aware Kraken/Oodle decoder loading.

The project ships the historical Linux extension for backwards compatibility,
while new installations should receive the platform-specific ``pyooz`` wheel.
Keeping resolution here makes unsupported platform errors explicit and keeps
the binary parser independent from import-time path manipulation.
"""

from __future__ import annotations

import importlib
import platform
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Callable


PYOOZ_VERSION = "0.0.8"
MAX_UNPACKED_SIZE = 512 * 1024 * 1024
_SUPPORTED_SYSTEMS = {"linux", "windows"}
_SUPPORTED_MACHINES = {"amd64", "x86_64"}


class CodecError(RuntimeError):
    """Raised when the native Kraken/Oodle decoder cannot be used safely."""


Importer = Callable[[str], Any]


def _normalise_system(value: str) -> str:
    return value.strip().lower()


def _normalise_machine(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def default_vendor_dir() -> Path:
    """Return the repository's legacy Linux extension directory."""

    return Path(__file__).resolve().parent.parent / "vendor"


def _unsupported_message(system: str, machine: str) -> str:
    return (
        f"Платформа {system or '<unknown>'}/{machine or '<unknown>'} не поддерживается. "
        "Нужны Linux или Windows x86_64/AMD64 и зависимость "
        f"pyooz=={PYOOZ_VERSION}."
    )


def _missing_message(system: str, machine: str, detail: BaseException) -> str:
    hint = f"pyooz=={PYOOZ_VERSION}"
    if system == "linux":
        hint += " или legacy vendor/ooz.abi3.so"
    return (
        f"Не удалось загрузить decoder для {system or '<unknown>'}/{machine or '<unknown>'}: "
        f"{hint} ({type(detail).__name__}: {detail})."
    )


def load_decoder(
    *,
    importer: Importer | None = None,
    system: str | None = None,
    machine: str | None = None,
    vendor_dir: Path | None = None,
) -> ModuleType | Any:
    """Load the native ``ooz`` module for the current supported target.

    ``importer``, ``system`` and ``machine`` are injectable so tests can cover
    missing wheels, wrong architectures and the Linux compatibility fallback
    without pretending that a Linux process is a Windows runner.
    """

    raw_system = platform.system() if system is None else system
    raw_machine = platform.machine() if machine is None else machine
    normal_system = _normalise_system(raw_system)
    normal_machine = _normalise_machine(raw_machine)
    display_system = raw_system.strip() or "<unknown>"
    display_machine = raw_machine.strip() or "<unknown>"

    if normal_system not in _SUPPORTED_SYSTEMS or normal_machine not in _SUPPORTED_MACHINES:
        raise CodecError(_unsupported_message(display_system, display_machine))

    import_module = importer or importlib.import_module
    try:
        return import_module("ooz")
    except Exception as first_error:
        if normal_system != "linux":
            raise CodecError(
                _missing_message(display_system, display_machine, first_error)
            ) from first_error

        legacy_dir = Path(vendor_dir) if vendor_dir is not None else default_vendor_dir()
        legacy_binary = legacy_dir / "ooz.abi3.so"
        if not legacy_binary.is_file():
            raise CodecError(
                _missing_message(display_system, display_machine, first_error)
            ) from first_error

        legacy_text = str(legacy_dir)
        if legacy_text not in sys.path:
            sys.path.insert(0, legacy_text)
        try:
            return import_module("ooz")
        except Exception as second_error:
            raise CodecError(
                _missing_message(display_system, display_machine, second_error)
            ) from second_error


def decompress(
    stream: bytes,
    unpacked_size: int,
    *,
    decoder: Any | None = None,
) -> bytes:
    """Decode one Kraken stream and require the advertised output length."""

    if not isinstance(stream, (bytes, bytearray, memoryview)):
        raise CodecError("Decoder получил поток не в bytes-подобном виде")
    if not isinstance(unpacked_size, int) or isinstance(unpacked_size, bool):
        raise CodecError("Размер распакованного потока должен быть целым числом")
    if unpacked_size <= 0 or unpacked_size > MAX_UNPACKED_SIZE:
        raise CodecError(f"Недопустимый размер распакованного потока: {unpacked_size}")

    native = decoder if decoder is not None else load_decoder()
    native_decompress = getattr(native, "decompress", None)
    if not callable(native_decompress):
        raise CodecError("Загруженный decoder не предоставляет decompress(stream, size)")
    try:
        result = native_decompress(bytes(stream), unpacked_size)
    except Exception as exc:
        raise CodecError(f"Native decoder завершился ошибкой: {exc}") from exc
    if not isinstance(result, (bytes, bytearray, memoryview)):
        raise CodecError("Native decoder вернул не bytes-подобный результат")
    raw = bytes(result)
    if len(raw) != unpacked_size:
        raise CodecError(
            f"Неверный размер после decoder: {len(raw)} вместо {unpacked_size}"
        )
    return raw
