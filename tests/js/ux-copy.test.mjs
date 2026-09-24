import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

import {
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
    "Мы не стали записывать изменения, потому что файл не прошёл проверку.",
  );
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
    "Технические детали: Код ошибки: VERIFY_FAILED\nSHA-256: abc",
  );
  assert.equal(technicalDetails(""), "");
});

test("browser screens hide implementation jargon from ordinary copy", async () => {
  const html = await readFile(new URL("../../web/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../../web/app.js", import.meta.url), "utf8");

  assert.match(html, /placeholder="Поиск предметов…"/);
  assert.match(
    html,
    /Веб-версия сохраняет только новую копию\. Исходный файл не изменяется\./,
  );
  assert.doesNotMatch(html, /автоматического повтора не будет/);
  for (const term of ["type-key", "handle…", "READ-ONLY", "immutable output", "uncertain write", "native paths", "DESKTOP ONLY"]) {
    assert.equal(html.toLowerCase().includes(term.toLowerCase()), false, `visible HTML contains ${term}`);
  }
  for (const term of ["READ-ONLY", "CRC PASS", "CRC FAIL", "read-only evidence", "immutable output"]) {
    assert.equal(app.includes(term), false, `browser UI copy contains ${term}`);
  }
});
