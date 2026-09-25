from __future__ import annotations

from ui.formatting import human_size


def test_human_size_uses_binary_units_for_qt_views() -> None:
    assert human_size(0) == "0 Б"
    assert human_size(1023) == "1023 Б"
    assert human_size(1024) == "1.0 КБ"
    assert human_size(1024 * 1024) == "1.0 МБ"
    assert human_size(1024**3) == "1.0 ГБ"
