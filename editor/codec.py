"""Platform-aware Kraken/Oodle decoder loading.

The project ships the historical Linux extension for backwards compatibility,
while new installations should receive the platform-specific ``pyooz`` wheel.
Keeping resolution here makes unsupported platform errors explicit and keeps
the binary parser independent from import-time path manipulation.
"""

from __future__ import annotations

import importlib
import platform
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

PYOOZ_VERSION = "0.0.8"
MAX_UNPACKED_SIZE = 512 * 1024 * 1024
_SUPPORTED_SYSTEMS = {"linux", "windows"}
_SUPPORTED_MACHINES = {"amd64", "x86_64"}


class CodecError(RuntimeError):
    """Raised when the native Kraken/Oodle decoder cannot be used safely."""


# A decoder installed by an embedder instead of being imported from a wheel.
# The browser build uses this: it runs CPython under WebAssembly, where there is
# no `ooz` wheel to import, and supplies a WASM decompressor from the host page.
# Keeping it an explicit registration - rather than letting the loader guess -
# means an unregistered embedder fails with a clear message instead of falling
# through to a platform check that was written for desktop wheels.
_registered_decoder: Any | None = None


def register_decoder(decoder: Any) -> None:
    """Install a decoder object exposing ``decompress(stream, size) -> bytes``."""

    if not callable(getattr(decoder, "decompress", None)):
        raise CodecError("Decoder должен предоставлять decompress(stream, size)")
    global _registered_decoder
    _registered_decoder = decoder


def clear_registered_decoder() -> None:
    """Forget an embedder-supplied decoder (used by tests)."""

    global _registered_decoder
    _registered_decoder = None


def registered_decoder() -> Any | None:
    """Return the embedder-supplied decoder, if one was registered."""

    return _registered_decoder


Importer = Callable[[str], Any]
EncoderImporter = Callable[[str], Any]


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

    if _registered_decoder is not None and system is None and machine is None:
        return _registered_decoder

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


def load_encoder(*, importer: EncoderImporter | None = None) -> Any:
    """Load the native Kraken encoder bundled with desktop builds."""

    import_module = importer or importlib.import_module
    try:
        encoder = import_module("ooz_encoder")
    except Exception as exc:
        raise CodecError(
            "Не удалось загрузить Kraken encoder: desktop build должен содержать "
            f"ooz_encoder ({type(exc).__name__}: {exc})"
        ) from exc
    if not callable(getattr(encoder, "compress", None)):
        raise CodecError("Загруженный Kraken encoder не предоставляет compress(raw, level)")
    return encoder


def compress(
    raw: bytes | bytearray | memoryview,
    *,
    encoder: Any | None = None,
    level: int = 5,
) -> bytes:
    """Encode a raw save payload as a framed Kraken stream."""

    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise CodecError("Encoder получил raw payload не в bytes-подобном виде")
    payload = bytes(raw)
    if not payload:
        raise CodecError("Нельзя сжать пустой raw payload")
    if len(payload) > MAX_UNPACKED_SIZE:
        raise CodecError(f"Недопустимый размер raw payload: {len(payload)}")
    if not isinstance(level, int) or isinstance(level, bool) or not -3 <= level <= 9:
        raise CodecError("Уровень Kraken должен быть целым числом от -3 до 9")

    native = encoder if encoder is not None else load_encoder()
    native_compress = getattr(native, "compress", None)
    if not callable(native_compress):
        raise CodecError("Загруженный encoder не предоставляет compress(raw, level)")
    try:
        result = native_compress(payload, level)
    except Exception as exc:
        raise CodecError(f"Native encoder завершился ошибкой: {exc}") from exc
    if not isinstance(result, (bytes, bytearray, memoryview)):
        raise CodecError("Native encoder вернул не bytes-подобный результат")
    encoded = bytes(result)
    if not encoded:
        raise CodecError("Native encoder вернул пустой Kraken stream")
    return encoded
