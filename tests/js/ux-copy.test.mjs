import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

import {
  BROWSER_UI_COPY,
  capabilityLabel,
  errorCopy,
  errorPresentation,
  integrityLabel,
  technicalDetails,
} from "../../web/ux_copy.js";

test("browser integrity copy hides CRC terminology", () => {
  assert.equal(integrityLabel({ crc_present: true, crc_ok: true }), "Файл проверен");
  assert.equal(integrityLabel({ crc_present: true, crc_ok: false }), "Файл повреждён или изменён");
  assert.equal(integrityLabel({ crc_present: false, integrity_name: "verified" }), "Файл проверен");
});

test("browser capabilities and errors use plain language", () => {
  assert.equal(capabilityLabel(true), "РЕДАКТИРУЕМЫЙ");
  assert.equal(capabilityLabel(false), "ТОЛЬКО ПРОСМОТР");
  assert.equal(errorCopy("open"), "Файл повреждён, не поддерживается или изменён другой программой.");
  assert.equal(
    errorCopy("verify"),
    "Изменения не были записаны, потому что файл не прошёл проверку.",
  );
  assert.equal(errorPresentation("generic").primaryAction, "Закрыть");
  assert.deepEqual(errorPresentation("open"), {
    errorCode: "ANALYSIS_FAILED",
    title: "Не удалось открыть сохранение",
    message: "Файл повреждён, не поддерживается или изменён другой программой.",
    severity: "error",
    primaryAction: "Выбрать другой файл",
    secondaryAction: "Подробнее",
    technicalDetails: null,
  });
  assert.equal(
    errorPresentation("verify").errorCode,
    "VERIFY_FAILED",
  );
  assert.equal(
    errorPresentation("open", "ENOENT: /private/save.sav").technicalDetails,
    "ENOENT: /private/save.sav",
  );
});

test("technical details remain explicitly separated", () => {
  assert.equal(
    technicalDetails("SHA-256: abc", "VERIFY_FAILED"),
    "Код ошибки: VERIFY_FAILED\nSHA-256: abc",
  );
  assert.equal(technicalDetails(""), "");
});

test("browser ordinary copy uses friendly startup and integrity labels", () => {
  assert.deepEqual(BROWSER_UI_COPY, {
    startupLoading: "Загрузка редактора…",
    startupPreparing: "Подготовка редактора…",
    integrity: "Проверка",
    integritySummary: "ПРОВЕРКА",
  });
});

test("browser screens hide implementation jargon from ordinary copy", async () => {
  const html = await readFile(new URL("../../web/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../../web/app.js", import.meta.url), "utf8");

  const visibleHtml = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
  const normalCopy = `${visibleHtml}\n${Object.values(BROWSER_UI_COPY).join("\n")}`;
  for (const term of [
    "Python-ядро",
    "декодер",
    "АНАЛИЗ ПО ЗАПРОСУ",
    "Целостность",
  ]) {
    assert.equal(
      normalCopy.toLocaleLowerCase("ru").includes(term.toLocaleLowerCase("ru")),
      false,
      `browser normal copy contains ${term}`,
    );
  }
  assert.equal(visibleHtml.includes("ПРОВЕРИТСЯ ПРИ ОТКРЫТИИ"), true);

  assert.match(html, /id="reference-library-search"[^>]+placeholder="Поиск сохранений…"/);
  assert.match(html, /id="reference-inventory-search"[^>]+placeholder="Поиск предметов…"/);
  assert.match(html, /id="reference-preview-status"[^>]*>НЕ ПРОВЕРЕНО<\/div>/);
  assert.match(html, /id="reference-editor-state"[^>]*>СОХРАНЕНИЕ НЕ ОТКРЫТО<\/span>/);
  assert.match(
    html,
    /Веб-версия сохраняет только новую копию\. Исходный файл не изменяется\./,
  );
  assert.match(html, /id="reference-technical-details"[^>]*>Технические детали/);
  assert.match(html, /<dialog[^>]+id="technical-details-dialog"/);
  assert.match(html, /<h2 id="technical-details-title">Технические детали<\/h2>/);
  assert.match(html, /id="technical-details-text" tabindex="0"/);
  assert.match(html, /id="technical-details-copy"[^>]*>Копировать/);
  assert.match(html, /id="technical-details-close"[^>]*>Закрыть/);
  assert.match(app, /detailsDialog\.showModal\(\)/);
  assert.doesNotMatch(app, /status\.title\s*=\s*technicalDetails/);
  assert.doesNotMatch(app, /\.title\s*=\s*technicalDetails/);
  assert.doesNotMatch(html, /автоматического повтора не будет/);
  for (const term of ["type-key", "handle…", "READ-ONLY", "immutable output", "uncertain write", "native paths", "DESKTOP ONLY"]) {
    assert.equal(html.toLowerCase().includes(term.toLowerCase()), false, `visible HTML contains ${term}`);
  }
  for (const term of ["READ-ONLY", "CRC PASS", "CRC FAIL", "read-only evidence", "immutable output"]) {
    assert.equal(app.includes(term), false, `browser UI copy contains ${term}`);
  }
});
