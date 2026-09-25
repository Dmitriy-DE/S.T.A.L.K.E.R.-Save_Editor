"""Centralized user messages with opt-in diagnostic details."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from editor.i18n import source_text, tr

MessageSeverity = Literal["info", "success", "warning", "error"]
ErrorKind = Literal[
    "open",
    "old_s2_save",
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
    secondary_action: str | None = tr("Подробнее")
    technical_details: str | None = None


CLOUD_COPY = {
    "write_intro": tr("Запись станет доступна только после безопасного подключения к Steam Cloud."),
    "selected": tr("Выбрано облачное сохранение. Открой его, чтобы начать редактирование."),
    "checked": tr("Сохранение проверено"),
    "uploaded": tr("Изменения успешно сохранены в Steam Cloud."),
    "uncertain": tr("Steam не подтвердил запись. Сначала проверь состояние облачного сохранения."),
}

BACKUP_STATUS_COPY = {
    "verified": tr("Готово к восстановлению"),
    "missing": tr("Файл не найден"),
    "corrupt": tr("Копия повреждена"),
}


ERROR_COPY: dict[ErrorKind, ErrorCopy] = {
    "open": ErrorCopy(
        error_code="ANALYSIS_FAILED",
        title=tr("Не удалось открыть сохранение"),
        message=tr("Файл повреждён, не поддерживается или изменён другой программой."),
        severity="error",
        primary_action=tr("Выбрать другой файл"),
    ),
    "old_s2_save": ErrorCopy(
        error_code="S2_LEGACY_LAYOUT",
        title=tr("Сохранение старой версии игры"),
        message=(
            tr("Похоже, это сохранение S.T.A.L.K.E.R. 2 из версии конца 2024 года. Загрузи его в игре и сохрани заново — после этого редактор его откроет.")
        ),
        severity="warning",
        primary_action=tr("Выбрать другой файл"),
    ),
    "corrupt": ErrorCopy(
        error_code="SAVE_CORRUPT",
        title=tr("Сохранение повреждено"),
        message=(
            tr("Файл не прошёл проверку. Редактирование отключено, чтобы не повредить его ещё сильнее.")
        ),
        severity="error",
        primary_action=tr("Выбрать другой файл"),
    ),
    "source_changed": ErrorCopy(
        error_code="SOURCE_CHANGED",
        title=tr("Не удалось сохранить изменения"),
        message=tr("Файл изменился после открытия. Открой его заново и повтори изменения."),
        severity="error",
        primary_action=tr("Открыть заново"),
    ),
    "backup": ErrorCopy(
        error_code="BACKUP_FAILED",
        title=tr("Не удалось создать резервную копию"),
        message=tr("Сохранение не изменено. Проверь доступ к папке резервных копий."),
        severity="error",
        primary_action=tr("Открыть настройки"),
    ),
    "verify": ErrorCopy(
        error_code="VERIFY_FAILED",
        title=tr("Не удалось проверить сохранение"),
        message=tr("Изменения не были записаны, потому что файл не прошёл проверку."),
        severity="error",
        primary_action=tr("Вернуться в редактор"),
    ),
    "unsupported": ErrorCopy(
        error_code="FORMAT_UNSUPPORTED",
        title=tr("Эта версия пока не поддерживается"),
        message=(
            tr("Сохранение распознано, но безопасное редактирование для этой версии ещё не готово.")
        ),
        severity="warning",
        primary_action=tr("Вернуться в библиотеку"),
        secondary_action=None,
    ),
    "cloud_unavailable": ErrorCopy(
        error_code="CLOUD_UNAVAILABLE",
        title=tr("Steam Cloud недоступен"),
        message=(
            tr("Не удалось подключиться к Steam Cloud. Локальные сохранения по-прежнему доступны.")
        ),
        severity="error",
        primary_action=tr("Повторить"),
        secondary_action=None,
    ),
    "cloud_write_unavailable": ErrorCopy(
        error_code="CLOUD_WRITE_UNAVAILABLE",
        title=tr("Запись в Steam Cloud недоступна"),
        message=tr("Запись в Steam Cloud сейчас недоступна."),
        severity="error",
        primary_action=tr("Повторить"),
    ),
    "cloud_uncertain": ErrorCopy(
        error_code="CLOUD_WRITE_UNCERTAIN",
        title=tr("Steam не подтвердил сохранение"),
        message=(
            tr("Неясно, записались ли изменения. Мы не будем повторять запись автоматически.")
        ),
        severity="warning",
        primary_action=tr("Проверить Steam Cloud"),
    ),
    "post_save_check": ErrorCopy(
        error_code="SAVE_RECHECK_FAILED",
        title=tr("Не удалось проверить сохранение"),
        message=(
            tr("Запись могла завершиться. Открой файл заново, прежде чем продолжить редактирование.")
        ),
        severity="error",
        primary_action=tr("Открыть заново"),
    ),
    "generic": ErrorCopy(
        error_code="ACTION_FAILED",
        title=tr("Не удалось выполнить действие"),
        message=tr("Попробуй ещё раз. Если проблема повторится, открой технические детали."),
        severity="error",
        primary_action=tr("Закрыть"),
    ),
}

SAVE_SUCCESS = ErrorCopy(
    error_code="SAVE_SUCCESS",
    title=tr("Изменения сохранены"),
    message=tr("Сохранение записано и проверено. Резервная копия создана."),
    severity="success",
    primary_action=tr("Вернуться к редактору"),
    secondary_action=tr("История"),
)


def present_error(kind: ErrorKind, details: str | None = None) -> ErrorCopy:
    """Return stable user copy paired with raw details kept off the main surface."""

    return replace(ERROR_COPY[kind], technical_details=details or None)


def technical_details(value: object) -> str:
    """Return diagnostic text for the dialog body, whose title labels the section."""

    return str(value) if value else ""


def format_error_details(presentation: ErrorCopy) -> str:
    """Expose a stable error code only inside the secondary detail layer."""

    details = [tr("Код ошибки: {0}", presentation.error_code)]
    if presentation.technical_details:
        details.append(presentation.technical_details)
    return "\n".join(details)


def classify_operation_error(message: str) -> ErrorKind:
    """Map known internal failures to the requested concise UI state."""

    value = source_text(str(message)).casefold()
    cloud = "cloud" in value or "облак" in value
    if cloud and any(
        token in value for token in ("uncertain", "не подтвержд", "uncertainty", "неясно")
    ):
        return "cloud_uncertain"
    if cloud and any(
        token in value
        for token in (
            "writer unavailable",
            "writer недоступ",
            "запись недоступ",
            "upload недоступ",
            "запись в облако недоступ",
            "запись в облако отключ",
        )
    ):
        return "cloud_write_unavailable"
    if cloud and any(
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

    value = source_text(str(message)).casefold()
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
    # The only S2 detector refusal seen on real saves: launch-build (v1.0.x)
    # slots keep the wallet GUID in an older layout.
    if "legacy s2 layout" in value:
        return "old_s2_save"
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
