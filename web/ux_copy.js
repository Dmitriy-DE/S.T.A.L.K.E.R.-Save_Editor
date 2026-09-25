import { t } from "./i18n.js";

const COPY = Object.freeze({
  open: Object.freeze({
    errorCode: "ANALYSIS_FAILED",
    title: t("Не удалось открыть сохранение"),
    message: t("Файл повреждён, не поддерживается или изменён другой программой."),
    severity: "error",
    primaryAction: t("Выбрать другой файл"),
    secondaryAction: t("Подробнее"),
  }),
  verify: Object.freeze({
    errorCode: "VERIFY_FAILED",
    title: t("Не удалось проверить сохранение"),
    message: t("Изменения не были записаны, потому что файл не прошёл проверку."),
    severity: "error",
    primaryAction: t("Вернуться в редактор"),
    secondaryAction: t("Подробнее"),
  }),
  generic: Object.freeze({
    errorCode: "ACTION_FAILED",
    title: t("Не удалось выполнить действие"),
    message: t("Попробуй ещё раз. Если проблема повторится, открой технические детали."),
    severity: "error",
    primaryAction: t("Закрыть"),
    secondaryAction: t("Подробнее"),
  }),
});

export const BROWSER_UI_COPY = Object.freeze({
  startupLoading: t("Загрузка редактора…"),
  startupPreparing: t("Подготовка редактора…"),
  integrity: t("Проверка"),
  integritySummary: t("ПРОВЕРКА"),
});

export function integrityLabel(info) {
  if (info?.crc_present === false) {
    const label = String(info.integrity_name ?? "").toLowerCase();
    return label.includes("fail") || label.includes("invalid")
      ? t("Файл повреждён или изменён")
      : t("Файл проверен");
  }
  return info?.crc_ok === false
    ? t("Файл повреждён или изменён")
    : t("Файл проверен");
}

export function capabilityLabel(editable) {
  return editable ? t("МОЖНО ИЗМЕНЯТЬ") : t("ТОЛЬКО ЧТЕНИЕ");
}

export function errorCopy(kind = "generic") {
  return errorPresentation(kind).message;
}

export function errorPresentation(kind = "generic", details = null) {
  return Object.freeze({
    ...(COPY[kind] ?? COPY.generic),
    technicalDetails: details ? String(details) : null,
  });
}

export function technicalDetails(value, errorCode = null) {
  if (!value) return "";
  const code = errorCode ? t("Код ошибки: {0}\n", errorCode) : "";
  return `${code}${value}`;
}
