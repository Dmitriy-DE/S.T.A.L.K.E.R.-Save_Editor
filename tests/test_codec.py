from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

import editor.codec as codec


class _Decoder:
    def __init__(self, payload: bytes = b"decoded") -> None:
        self.payload = payload
        self.calls: list[tuple[bytes, int]] = []

    def decompress(self, stream: bytes, unpacked_size: int) -> bytes:
        self.calls.append((stream, unpacked_size))
        return self.payload


def test_decompress_uses_injected_decoder() -> None:
    decoder = _Decoder(b"decoded")

    result = codec.decompress(b"packed", 7, decoder=decoder)

    assert result == b"decoded"
    assert decoder.calls == [(b"packed", 7)]


def test_decompress_wraps_native_error() -> None:
    class Broken:
        def decompress(self, stream: bytes, unpacked_size: int) -> bytes:
            raise OSError("native failure")

    with pytest.raises(codec.CodecError, match="decoder"):
        codec.decompress(b"packed", 7, decoder=Broken())


def test_decompress_rejects_wrong_output_size() -> None:
    with pytest.raises(codec.CodecError, match="размер"):
        codec.decompress(b"packed", 7, decoder=_Decoder(b"short"))


def test_load_decoder_prefers_platform_installed_module() -> None:
    decoder = _Decoder()
    calls: list[str] = []

    def importer(name: str):
        calls.append(name)
        return decoder

    loaded = codec.load_decoder(
        importer=importer,
        system="Windows",
        machine="AMD64",
        vendor_dir=Path("/does/not/exist"),
    )

    assert loaded is decoder
    assert calls == ["ooz"]


def test_load_decoder_linux_falls_back_to_legacy_vendor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "ooz.abi3.so").write_bytes(b"placeholder")
    decoder = _Decoder()
    calls = 0

    def importer(name: str):
        nonlocal calls
        assert name == "ooz"
        calls += 1
        if calls == 1:
            raise ImportError("pyooz is not installed")
        return decoder

    original_path = list(sys.path)
    monkeypatch.setattr(sys, "path", original_path.copy())
    loaded = codec.load_decoder(
        importer=importer,
        system="Linux",
        machine="x86_64",
        vendor_dir=vendor_dir,
    )

    assert loaded is decoder
    assert calls == 2
    assert str(vendor_dir) in sys.path


def test_load_decoder_never_adds_linux_vendor_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    (vendor_dir / "ooz.abi3.so").write_bytes(b"placeholder")

    original_path = list(sys.path)
    monkeypatch.setattr(sys, "path", original_path.copy())

    def importer(name: str):
        raise ImportError("no compatible wheel")

    with pytest.raises(codec.CodecError, match=r"Windows.*AMD64.*pyooz==0\.0\.8"):
        codec.load_decoder(
            importer=importer,
            system="Windows",
            machine="AMD64",
            vendor_dir=vendor_dir,
        )

    assert str(vendor_dir) not in sys.path


def test_load_decoder_rejects_unsupported_platform_and_architecture() -> None:
    calls: list[str] = []

    def importer(name: str):
        calls.append(name)
        return _Decoder()

    with pytest.raises(codec.CodecError, match=r"Darwin.*x86_64.*не поддерживается"):
        codec.load_decoder(importer=importer, system="Darwin", machine="x86_64")

    with pytest.raises(codec.CodecError, match=r"Linux.*aarch64.*не поддерживается"):
        codec.load_decoder(importer=importer, system="Linux", machine="aarch64")

    assert calls == []


def test_pyooz_provenance_records_linux_and_windows_wheels() -> None:
    path = Path(__file__).parents[1] / "third_party" / "pyooz" / "provenance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = {entry["filename"] for entry in payload["files"]}

    assert "pyooz-0.0.8-cp38-abi3-win_amd64.whl" in names
    assert any("manylinux_2_17_x86_64" in name for name in names)
    assert all(re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) for entry in payload["files"])
