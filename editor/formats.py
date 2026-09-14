"""Static save-format registry shared by every editor front end."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from save_format import SaveError, SaveInfo, inspect_save

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
class DetectionFailure:
    """Why one registered format rejected a byte sequence."""

    format_id: str
    format_title: str
    reason: str


@dataclass(frozen=True)
class FormatInspection:
    """Inspection result plus the format metadata selected for its bytes."""

    format_id: str
    format_title: str
    info: SaveInfo


class FormatDetectionError(SaveError):
    """A stable, user-facing error for bytes no registered format accepts."""

    def __init__(
        self,
        *,
        display_name: str,
        size: int,
        failures: tuple[DetectionFailure, ...],
        supported: tuple[SaveFormat, ...],
    ) -> None:
        self.display_name = display_name
        self.size = size
        self.failures = failures
        self.supported = supported
        reasons = "; ".join(
            f"{failure.format_id} ({failure.format_title}) — {failure.reason}"
            for failure in failures
        ) or "зарегистрированные форматы отсутствуют"
        supported_text = ", ".join(
            f"{format_.id} — {format_.title}" for format_ in supported
        ) or "нет зарегистрированных форматов"
        super().__init__(
            f"Error: Формат файла {display_name!r} не распознан "
            f"(размер: {size} байт). Причины: {reasons}. "
            f"Поддерживаются сейчас: {supported_text}."
        )


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

    def detection_reason(self, data: bytes) -> str:
        try:
            info = inspect_save(data, with_inventory=False)
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        return (
            "подтверждённая wallet anchor встречается "
            f"{info.money_anchor_count} раз(а), ожидалась ровно 1"
        )

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


def detection_failures(data: bytes) -> tuple[DetectionFailure, ...]:
    """Return per-format reasons without letting malformed input escape."""

    failures: list[DetectionFailure] = []
    for fmt in _REGISTERED_FORMATS:
        try:
            if fmt.detect(data):
                return ()
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
        else:
            reason_fn = getattr(fmt, "detection_reason", None)
            if callable(reason_fn):
                try:
                    reason = str(reason_fn(data))
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
            else:
                reason = "сигнатура не подтверждена"
        failures.append(DetectionFailure(fmt.id, fmt.title, reason))
    return tuple(failures)


def format_detection_error(
    data: bytes, *, display_name: str | None = None
) -> FormatDetectionError:
    """Build the shared diagnostic raised for an unknown save format."""

    label = display_name.strip() if display_name and display_name.strip() else "<без имени>"
    return FormatDetectionError(
        display_name=label,
        size=len(data),
        failures=detection_failures(data),
        supported=formats(),
    )


def detect_or_raise(data: bytes, *, display_name: str | None = None) -> SaveFormat:
    """Resolve a format or raise the shared, user-facing diagnostic."""

    format_ = detect(data)
    if format_ is None:
        raise format_detection_error(data, display_name=display_name)
    return format_


register(STALKER2_FORMAT)


__all__ = [
    "STALKER2_FORMAT",
    "DetectionFailure",
    "FormatDetectionError",
    "FormatInspection",
    "SaveFormat",
    "by_id",
    "detect",
    "detect_or_raise",
    "detection_failures",
    "format_detection_error",
    "formats",
    "register",
]
