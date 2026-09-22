from __future__ import annotations

import json

import editor.codec as codec
from ui.__main__ import diagnostic_main


def test_diagnostic_cli_encoder_smoke_reports_round_trip(
    monkeypatch, capsys
) -> None:
    class FakeDecoder:
        __file__ = "<fake-decoder>"

    class FakeEncoder:
        __file__ = "<fake-encoder>"

    monkeypatch.setattr(codec, "load_decoder", lambda: FakeDecoder())
    monkeypatch.setattr(codec, "load_encoder", lambda: FakeEncoder())
    payload: dict[str, bytes] = {}

    def fake_compress(raw: bytes, **_kwargs) -> bytes:
        payload["raw"] = raw
        return b"packed"

    monkeypatch.setattr(codec, "compress", fake_compress)
    monkeypatch.setattr(
        codec,
        "decompress",
        lambda _stream, size, **_kwargs: payload["raw"][:size],
    )

    assert diagnostic_main(["--diagnostic", "--encoder-smoke"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["decoder"] == "loaded"
    assert report["encoder"] == "loaded"
    assert report["encoder_round_trip"] is True
    assert report["encoder_packed_bytes"] > 0
