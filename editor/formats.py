"""Static save-format registry shared by every editor front end."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from save_format import SaveInfo, inspect_save

from .models import EditPlan, PreparedEdit
from .prepare import prepare_edit


class SaveFormat(Protocol):
    """The read and write contract for one save-file format."""

    id: str
    title: str

    def detect(self, data: bytes) -> bool:
        """Return whether ``data`` belongs to this format."""

    def inspect(self, data: bytes, *, with_inventory: bool = True) -> SaveInfo:
        """Inspect bytes without modifying them."""

    def prepare(self, data: bytes, plan: EditPlan) -> PreparedEdit:
        """Prepare an immutable edit for bytes in this format."""


@dataclass(frozen=True)
class FormatInspection:
    """Inspection result plus the format metadata selected for its bytes."""

    format_id: str
    format_title: str
    info: SaveInfo


class _Stalker2Format:
    id = "stalker2"
    title = "S.T.A.L.K.E.R. 2: Heart of Chornobyl"

    def detect(self, data: bytes) -> bool:
        """Recognize the confirmed S.T.A.L.K.E.R. 2 container signature.

        Detection is deliberately defensive: arbitrary foreign bytes are an
        expected input to this method and must never escape parser exceptions.
        The existing parser's unique money anchor is the only confirmed
        content marker available to M01.
        """

        try:
            info = inspect_save(data, with_inventory=False)
        except Exception:
            return False
        return info.money_anchor_count == 1

    def inspect(self, data: bytes, *, with_inventory: bool = True) -> SaveInfo:
        return inspect_save(data, with_inventory=with_inventory)

    def prepare(self, data: bytes, plan: EditPlan) -> PreparedEdit:
        return prepare_edit(data, plan)


STALKER2_FORMAT: SaveFormat = _Stalker2Format()
_REGISTERED_FORMATS: list[SaveFormat] = []


def register(fmt: SaveFormat) -> None:
    """Register one static format, rejecting duplicate identifiers."""

    if any(existing.id == fmt.id for existing in _REGISTERED_FORMATS):
        raise ValueError(f"Format ID already registered: {fmt.id!r}")
    _REGISTERED_FORMATS.append(fmt)


def formats() -> tuple[SaveFormat, ...]:
    """Return the registered formats in deterministic registration order."""

    return tuple(_REGISTERED_FORMATS)


def by_id(format_id: str) -> SaveFormat:
    """Return a format by ID or raise ``KeyError`` for an unknown ID."""

    for fmt in _REGISTERED_FORMATS:
        if fmt.id == format_id:
            return fmt
    raise KeyError(format_id)


def detect(data: bytes) -> SaveFormat | None:
    """Return the first format accepting ``data``, or ``None``."""

    for fmt in _REGISTERED_FORMATS:
        try:
            if fmt.detect(data):
                return fmt
        except Exception:
            # A foreign or malformed file must not prevent other registered
            # formats from getting a chance to inspect its bytes.
            continue
    return None


register(STALKER2_FORMAT)


__all__ = [
    "STALKER2_FORMAT",
    "FormatInspection",
    "SaveFormat",
    "by_id",
    "detect",
    "formats",
    "register",
]
