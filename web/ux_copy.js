const COPY = Object.freeze({
  open: Object.freeze({
    errorCode: "ANALYSIS_FAILED",
    title: "Не удалось открыть сохранение",
    message: "Файл повреждён, не поддерживается или изменён другой программой.",
    severity: "error",
    primaryAction: "Выбрать другой файл",
    secondaryAction: "Подробнее",
  }),
  verify: Object.freeze({
    errorCode: "VERIFY_FAILED",
    title: "Не удалось проверить сохранение",
    message: "Изменения не были записаны, потому что файл не прошёл проверку.",
    severity: "error",
    primaryAction: "Вернуться в редактор",
    secondaryAction: "Подробнее",
  }),
  generic: Object.freeze({
    errorCode: "ACTION_FAILED",
    title: "Не удалось выполнить действие",
    message: "Попробуй ещё раз. Если проблема повторится, открой технические детали.",
    severity: "error",
    primaryAction: "Закрыть",
    secondaryAction: "Подробнее",
  }),
});

export const BROWSER_UI_COPY = Object.freeze({
  startupLoading: "Загрузка редактора…",
  startupPreparing: "Подготовка редактора…",
  integrity: "Проверка",
  integritySummary: "ПРОВЕРКА",
});

export function integrityLabel(info) {
  if (info?.crc_present === false) {
    const label = String(info.integrity_name ?? "").toLowerCase();
    return label.includes("fail") || label.includes("invalid")
      ? "Файл повреждён или изменён"
      : "Файл проверен";
  }
  return info?.crc_ok === false
    ? "Файл повреждён или изменён"
    : "Файл проверен";
}

export function capabilityLabel(editable) {
  return editable ? "МОЖНО ИЗМЕНЯТЬ" : "ТОЛЬКО ЧТЕНИЕ";
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
  const code = errorCode ? `Код ошибки: ${errorCode}\n` : "";
  return `${code}${value}`;
}
