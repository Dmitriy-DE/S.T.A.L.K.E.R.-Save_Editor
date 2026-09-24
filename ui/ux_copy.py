"""Centralized user messages with opt-in diagnostic details."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

MessageSeverity = Literal["info", "success", "warning", "error"]
ErrorKind = Literal[
    "open",
    "corrupt",
    "source_changed",
    "backup",
    "verify",
    "unsupported",
    "cloud_unavailable",
    "cloud_write_unavailable",
    "cloud_uncertain",
    "post_save_check",
    "generic",
]


@dataclass(frozen=True)
class ErrorCopy:
    """Human-readable state and its separately held diagnostic context."""

    error_code: str
    title: str
    message: str
    severity: MessageSeverity
    primary_action: str
    secondary_action: str | None = "Подробнее"
    technical_details: str | None = None


ERROR_COPY: dict[ErrorKind, ErrorCopy] = {
    "open": ErrorCopy(
        error_code="ANALYSIS_FAILED",
        title="Не удалось открыть сохранение",
        message="Файл повреждён, не поддерживается или изменён другой программой.",
        severity="error",
        primary_action="Выбрать другой файл",
    ),
    "corrupt": ErrorCopy(
        error_code="SAVE_CORRUPT",
        title="Сохранение повреждено",
        message=(
            "Файл не прошёл проверку. Редактирование отключено, "
            "чтобы не повредить его ещё сильнее."
        ),
        severity="error",
        primary_action="Выбрать другой файл",
    ),
    "source_changed": ErrorCopy(
        error_code="SOURCE_CHANGED",
        title="Не удалось сохранить изменения",
        message="Файл изменился после открытия. Открой его заново и повтори изменения.",
        severity="error",
        primary_action="Открыть заново",
    ),
    "backup": ErrorCopy(
        error_code="BACKUP_FAILED",
        title="Не удалось создать резервную копию",
        message="Сохранение не изменено. Проверь доступ к папке резервных копий.",
        severity="error",
        primary_action="Открыть настройки",
    ),
    "verify": ErrorCopy(
        error_code="VERIFY_FAILED",
        title="Не удалось проверить сохранение",
        message="Мы не стали записывать изменения, потому что файл не прошёл проверку.",
        severity="error",
        primary_action="Вернуться в редактор",
    ),
    "unsupported": ErrorCopy(
        error_code="FORMAT_UNSUPPORTED",
        title="Эта версия пока не поддерживается",
        message=(
            "Сохранение распознано, но безопасное редактирование для этой версии "
            "ещё не готово."
        ),
        severity="warning",
        primary_action="Вернуться в библиотеку",
        secondary_action=None,
    ),
    "cloud_unavailable": ErrorCopy(
        error_code="CLOUD_UNAVAILABLE",
        title="Steam Cloud недоступен",
        message=(
            "Не удалось подключиться к Steam Cloud. "
            "Локальные сохранения по-прежнему доступны."
        ),
        severity="error",
        primary_action="Повторить",
        secondary_action=None,
    ),
    "cloud_write_unavailable": ErrorCopy(
        error_code="CLOUD_WRITE_UNAVAILABLE",
        title="Запись в Steam Cloud недоступна",
        message="Запись в Steam Cloud сейчас недоступна.",
        severity="error",
        primary_action="Повторить",
    ),
    "cloud_uncertain": ErrorCopy(
        error_code="CLOUD_WRITE_UNCERTAIN",
        title="Steam не подтвердил сохранение",
        message=(
            "Неясно, записались ли изменения. "
            "Мы не будем повторять запись автоматически."
        ),
        severity="warning",
        primary_action="Проверить Steam Cloud",
    ),
    "post_save_check": ErrorCopy(
        error_code="SAVE_RECHECK_FAILED",
        title="Не удалось проверить сохранение",
        message=(
            "Запись могла завершиться. Открой файл заново, "
            "прежде чем продолжить редактирование."
        ),
        severity="error",
        primary_action="Открыть заново",
    ),
    "generic": ErrorCopy(
        error_code="ACTION_FAILED",
        title="Не удалось выполнить действие",
        message="Попробуй ещё раз. Если проблема повторится, открой технические детали.",
        severity="error",
        primary_action="Вернуться в редактор",
    ),
}

SAVE_SUCCESS = ErrorCopy(
    error_code="SAVE_SUCCESS",
    title="Изменения сохранены",
    message="Сохранение записано и проверено. Резервная копия создана.",
    severity="success",
    primary_action="Вернуться к редактору",
    secondary_action="История",
)


def present_error(kind: ErrorKind, details: str | None = None) -> ErrorCopy:
    """Return stable user copy paired with raw details kept off the main surface."""

    return replace(ERROR_COPY[kind], technical_details=details or None)


def technical_details(value: object) -> str:
    """Label explicitly requested diagnostic text without putting it in normal copy."""

    return f"Технические детали:\n{value}" if value else ""


def format_error_details(presentation: ErrorCopy) -> str:
    """Expose a stable error code only inside the secondary detail layer."""

    details = [f"Код ошибки: {presentation.error_code}"]
    if presentation.technical_details:
        details.append(presentation.technical_details)
    return technical_details("\n".join(details))


def classify_operation_error(message: str) -> ErrorKind:
    """Map known internal failures to the requested concise UI state."""

    value = str(message).casefold()
    if "cloud" in value and any(
        token in value for token in ("uncertain", "не подтвержд", "uncertainty", "неясно")
    ):
        return "cloud_uncertain"
    if "cloud" in value and any(
        token in value
        for token in ("writer unavailable", "writer недоступ", "запись недоступ", "upload недоступ")
    ):
        return "cloud_write_unavailable"
    if "cloud" in value and any(
        token in value for token in ("connect", "подключ", "transport", "недоступ")
    ):
        return "cloud_unavailable"
    if any(token in value for token in ("source sha", "источник изменился", "source changed")):
        return "source_changed"
    if any(token in value for token in ("backup", "резервн")) and any(
        token in value
        for token in (
            "не удалось создать",
            "не удалось подготовить",
            "не удалось записать",
            "backup directory",
            "backup paths",
            "backup недоступен",
            "backup failed",
        )
    ):
        return "backup"
    if any(
        token in value
        for token in (
            "crc",
            "sha",
            "round-trip",
            "round trip",
            "не прошла провер",
            "не прошёл провер",
        )
    ):
        return "verify"
    return "generic"


def classify_analysis_error(message: str) -> ErrorKind:
    """Distinguish a file-integrity failure from other open failures."""

    value = str(message).casefold()
    if any(
        token in value
        for token in (
            "crc mismatch",
            "crc fail",
            "checksum mismatch",
            "checksum failed",
            "checksum failure",
            "контрольная сумма не совпала",
            "контрольная сумма не прошла",
        )
    ):
        return "corrupt"
    return "open"


__all__ = [
    "ERROR_COPY",
    "SAVE_SUCCESS",
    "ErrorCopy",
    "ErrorKind",
    "MessageSeverity",
    "classify_analysis_error",
    "classify_operation_error",
    "format_error_details",
    "present_error",
    "technical_details",
]
