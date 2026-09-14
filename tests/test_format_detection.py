from __future__ import annotations

from pathlib import Path

import pytest

import cli
from editor.formats import FormatDetectionError, detect
from editor.service import EditorService


@pytest.mark.parametrize(
    ("data_factory", "filename"),
    [
        (lambda _fixture: b"", "empty.sav"),
        (lambda fixture: fixture[:-1], "truncated.sav"),
        (lambda fixture: b"\x00" * len(fixture), "same-size-garbage.sav"),
        (lambda _fixture: b"\x7fELF\x02\x01\x01" + b"\x00" * 64, "foreign.sav"),
        (lambda _fixture: b"plain text that is not a save", "text.sav"),
    ],
)
def test_negative_inputs_are_not_detected(
    data_factory, filename: str, synthetic_save: bytes
) -> None:
    data = data_factory(synthetic_save)

    assert detect(data) is None
    with pytest.raises(FormatDetectionError) as caught:
        EditorService().inspect(data, source_name=filename)

    message = str(caught.value)
    assert filename in message
    assert str(len(data)) in message
    assert "stalker2" in message
    assert "Причины" in message
    assert "Поддерживаются сейчас" in message


def test_unknown_format_message_is_identical_in_cli_and_web(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = b"plain text that is not a save"
    name = "renamed-save.sav"
    path = tmp_path / name
    path.write_bytes(data)

    with pytest.raises(FormatDetectionError) as service_error:
        EditorService().inspect(data, source_name=name)
    expected = str(service_error.value)

    assert cli.main(["info", str(path)]) == 2
    assert capsys.readouterr().err.strip() == expected

    import sys

    sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
    import web_bridge

    with pytest.raises(FormatDetectionError) as web_error:
        web_bridge.analyze(data, name)
    assert str(web_error.value) == expected


def test_unknown_format_does_not_modify_the_source(
    tmp_path: Path, synthetic_save: bytes
) -> None:
    data = b"not a save"
    path = tmp_path / "unchanged.sav"
    path.write_bytes(data)

    assert cli.main(["info", str(path)]) == 2
    assert path.read_bytes() == data
