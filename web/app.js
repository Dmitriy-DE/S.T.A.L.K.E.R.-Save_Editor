// Browser build: the page is a thin shell around the project's own Python core.
//
// Pyodide runs the shared format registry unchanged.  ooz-wasm supplies the
// native decoder for S.T.A.L.K.E.R. 2; original X-Ray saves use the bundled
// pure-Python LZO reader.  Nothing is uploaded: the file stays in this tab.

const PYODIDE_VERSION = "0.28.3";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const OOZ_URL = "https://cdn.jsdelivr.net/npm/ooz-wasm@2.0.0/index.js";

const el = (id) => document.getElementById(id);
const status = el("status");

const state = {
  py: null,
  bridge: null,
  snapshot: null,
  money: null,
  stacks: new Map(),
  prepared: null,
};

function setStatus(text, kind = "") {
  status.textContent = text;
  status.className = `status${kind ? " " + kind : ""}`;
}

function fail(error) {
  console.error(error);
  setStatus(String(error && error.message ? error.message : error), "error");
}

async function boot() {
  setStatus("Загрузка декодера сохранений…", "busy");
  const ooz = await import(OOZ_URL);

  setStatus("Загрузка Python-ядра (Pyodide)…", "busy");
  const { loadPyodide } = await import(`${PYODIDE_URL}pyodide.mjs`);
  const py = await loadPyodide({ indexURL: PYODIDE_URL });

  setStatus("Установка ядра редактора…", "busy");
  const bundle = await (await fetch("pysrc.json")).json();
  py.FS.mkdirTree("/core/editor");
  for (const [name, source] of Object.entries(bundle.files)) {
    py.FS.writeFile(`/core/${name}`, source, { encoding: "utf8" });
  }
  py.FS.writeFile("/core/web_bridge.py", await (await fetch("web_bridge.py")).text(), {
    encoding: "utf8",
  });
  py.runPython(`import sys; sys.path.insert(0, "/core")`);

  // The decoder crosses the boundary once, as a plain function.
  globalThis.__oozDecompress = (stream, size) => ooz.decompress(stream, size);
  const bridge = py.pyimport("web_bridge");
  bridge.install_decoder(globalThis.__oozDecompress);

  state.py = py;
  state.bridge = bridge;
  el("core-state").textContent = "готово";
  el("footer-build").textContent =
    `Ядро: ${bundle.source_sha256.slice(0, 12)}… · Pyodide ${PYODIDE_VERSION} · ooz-wasm 2.0.0`;
  el("file-input").disabled = false;
  setStatus("Ядро готово. Открой локальный файл сохранения.");
}

async function openFile(file) {
  if (!state.bridge) return;
  setStatus(`Чтение ${file.name}…`, "busy");
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const t0 = performance.now();
    const snapshot = JSON.parse(state.bridge.analyze(bytes, file.name));
    const ms = Math.round(performance.now() - t0);

    state.snapshot = snapshot;
    state.money = null;
    state.stacks.clear();
    state.prepared = null;
    renderSnapshot(snapshot);
    setStatus(`Анализ завершён за ${ms} мс; snapshot готов`);
  } catch (error) {
    fail(error);
  }
}

function renderSnapshot(s) {
  el("source-badge").textContent = "ЛОКАЛЬНЫЙ ФАЙЛ";
  el("file-name").textContent = s.name;
  el("file-details").textContent = `${s.size_text} • SHA ${s.sha256.slice(0, 12)}…`;

  const crc = el("crc-badge");
  if (s.crc_present) {
    crc.textContent = `CRC-32: ${s.crc_ok ? "PASS" : "FAIL"}`;
    crc.className = `badge ${s.crc_ok ? "pass" : "fail"}`;
  } else {
    crc.textContent = `${s.integrity_name}: OK`;
    crc.className = "badge pass";
  }
  el("format-badge").textContent = `ФОРМАТ: ${s.format_title}`;

  el("card-location").textContent = s.level_name ?? "неизвестно";
  el("card-time").textContent = s.game_time === null ? "—" : String(s.game_time);
  el("card-money").textContent = s.money === null ? "—" : String(s.money);
  el("card-items").textContent = String(s.inventory_count);
  el("summary").textContent =
    `${s.crc_present ? `CRC: ${s.crc_ok ? "OK" : "FAIL"}` : `${s.integrity_name}: OK`} · ` +
    `Деньги: ${s.money ?? "неизвестно"} · ` +
    `Предметов: ${s.inventory_count}`;
  el("support").textContent =
    `Формат: ${s.format_title}. Поддержанные данные: деньги и снимок инвентаря; ` +
    "неизвестные поля остаются read-only." +
    (s.warnings.length ? ` Предупреждения: ${s.warnings.join(" ")}` : "");

  const body = el("metadata").tBodies[0];
  body.replaceChildren(...s.metadata.map((row) => {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      td.textContent = cell;
      if (cell.length > 40) td.className = "mono";
      tr.append(td);
    }
    return tr;
  }));

  const group = el("money-group");
  group.disabled = !s.money_editable;
  el("money-status").textContent = s.money_editable
    ? `${s.money} → ${s.money}`
    : "Только чтение: сигнатура кошелька не однозначна";
  if (s.money_editable) el("money-input").value = String(s.money);

  renderInventory();
  renderChanges();
}

function visibleItems() {
  const query = el("inventory-search").value.trim().toLowerCase();
  const filter = el("inventory-filter").value;
  return (state.snapshot?.inventory ?? []).filter((item) => {
    if (filter === "editable" && !item.editable) return false;
    if (filter === "readonly" && item.editable) return false;
    if (filter === "staged" && !state.stacks.has(item.handle)) return false;
    if (!query) return true;
    return [item.name, item.category, item.type_key, item.handle_hex]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

function renderInventory() {
  const body = el("inventory").tBodies[0];
  body.replaceChildren(...visibleItems().map((item) => {
    const tr = document.createElement("tr");
    const staged = state.stacks.get(item.handle);
    tr.className = staged !== undefined ? "staged" : item.editable ? "" : "readonly";
    for (const cell of [
      item.name, item.category, item.position, item.size_text, item.type_key,
      item.count === null ? "неизвестно" : String(item.count),
      item.total_weight === null ? "неизвестно" : item.total_weight.toFixed(3),
      item.handle_hex,
    ]) {
      const td = document.createElement("td");
      td.textContent = cell;
      tr.append(td);
    }
    const td = document.createElement("td");
    if (item.editable) {
      const input = document.createElement("input");
      input.type = "number";
      input.min = "1";
      input.max = String(state.snapshot.stack_max ?? 1000000);
      input.value = String(staged ?? item.count);
      input.addEventListener("change", () => {
        const value = Number(input.value);
        const max = Number(state.snapshot.stack_max ?? 1000000);
        if (!Number.isInteger(value) || value < 1 || value > max) {
          input.value = String(item.count);
          return;
        }
        if (value === item.count) state.stacks.delete(item.handle);
        else state.stacks.set(item.handle, value);
        invalidate();
        renderInventory();
        renderChanges();
      });
      td.append(input);
    } else {
      td.textContent = "только чтение";
      td.className = "muted";
    }
    tr.append(td);
    return tr;
  }));
}

function renderChanges() {
  const list = el("changes-list");
  const items = [];
  if (state.money !== null) {
    items.push(`Деньги: ${state.snapshot.money} → ${state.money}`);
  }
  for (const [handle, count] of state.stacks) {
    const item = state.snapshot.inventory.find((i) => i.handle === handle);
    items.push(`Стак ${item.handle_hex}: ${item.count} → ${count}`);
  }
  list.replaceChildren(...(items.length
    ? items.map((text) => {
        const li = document.createElement("li");
        li.textContent = text;
        return li;
      })
    : [Object.assign(document.createElement("li"), {
        className: "muted",
        textContent: "Изменений ещё нет",
      })]));

  const has = items.length > 0;
  el("preview").disabled = !has;
  el("money-clear").disabled = state.money === null;
  el("download").disabled = state.prepared === null;
}

function invalidate() {
  if (state.prepared !== null) {
    state.prepared = null;
    el("preview-status").textContent = "Предпросмотр сброшен: изменения обновились";
    el("preview-status").className = "muted";
    el("download").disabled = true;
  }
}

function preview() {
  try {
    setStatus("Применение изменений…", "busy");
    const stacks = JSON.stringify([...state.stacks.entries()]);
    const result = JSON.parse(state.bridge.prepare(state.money, stacks));
    state.prepared = result;

    const lines = [`Копия готова: ${result.size_text}, SHA ${result.output_sha256.slice(0, 12)}…`];
    if (result.money[0] !== result.money[1]) {
      lines.push(`деньги ${result.money[0]} → ${result.money[1]}`);
    }
    for (const [handle, before, after] of result.stacks) {
      lines.push(`${handle}: ${before} → ${after}`);
    }
    if (!result.source_unchanged) lines.push("ВНИМАНИЕ: исходные байты изменились");
    el("preview-status").textContent = lines.join(" · ");
    el("preview-status").className = "";
    el("download").disabled = false;
    setStatus("Предпросмотр выполнен; исходный файл не изменялся");
  } catch (error) {
    fail(error);
  }
}

function download() {
  try {
    const bytes = state.bridge.output_bytes().toJs();
    const match = state.snapshot.name.match(/\.(sav|scop|scs)$/i);
    const extension = match ? `.${match[1].toLowerCase()}` : ".sav";
    const name = state.snapshot.name.replace(/\.(sav|scop|scs)$/i, "") + "_edited" + extension;
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
    const link = Object.assign(document.createElement("a"), { href: url, download: name });
    link.click();
    URL.revokeObjectURL(url);
    setStatus(`Сохранена копия ${name}. Исходный файл не изменён.`);
  } catch (error) {
    fail(error);
  }
}

for (const button of document.querySelectorAll(".nav")) {
  button.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".nav")) {
      other.setAttribute("aria-current", String(other === button));
    }
    for (const panel of document.querySelectorAll(".panel")) {
      panel.hidden = panel.id !== `panel-${button.dataset.panel}`;
    }
  });
}

el("file-input").addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  if (file) openFile(file);
});
el("inventory-search").addEventListener("input", renderInventory);
el("inventory-filter").addEventListener("change", renderInventory);
el("money-stage").addEventListener("click", () => {
  const value = Number(el("money-input").value);
  if (!Number.isInteger(value) || value < 0 || value > 2_000_000_000) {
    setStatus("Сумма должна быть целым числом 0…2 000 000 000", "error");
    return;
  }
  state.money = value === state.snapshot.money ? null : value;
  el("money-status").textContent = `${state.snapshot.money} → ${state.money ?? state.snapshot.money}`;
  invalidate();
  renderChanges();
});
el("money-clear").addEventListener("click", () => {
  state.money = null;
  el("money-status").textContent = `${state.snapshot.money} → ${state.snapshot.money}`;
  el("money-input").value = String(state.snapshot.money);
  invalidate();
  renderChanges();
});
el("preview").addEventListener("click", preview);
el("download").addEventListener("click", download);

el("file-input").disabled = true;
boot().catch(fail);
