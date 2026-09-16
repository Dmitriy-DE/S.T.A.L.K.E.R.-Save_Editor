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
  durability: new Map(),
  relations: new Map(),
  playerFaction: null,
  adds: new Map(),
  detach: new Set(),
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
  const generatedCatalogs = await (await fetch("catalogs.json")).text();
  bridge.install_catalogs(generatedCatalogs);

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
    state.durability.clear();
    state.relations.clear();
    state.playerFaction = null;
    state.adds.clear();
    state.detach.clear();
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
  el("format-badge").textContent =
    `ФОРМАТ: ${s.format_title} · ${s.release_id} (${s.edition})`;
  el("preview-status").textContent = "Предпросмотр ещё не выполнен";
  el("preview-status").className = "muted";

  el("card-location").textContent = s.level_name ?? "неизвестно";
  el("card-time").textContent = s.game_time === null ? "—" : String(s.game_time);
  el("card-money").textContent = s.money === null ? "—" : String(s.money);
  el("card-items").textContent = String(s.inventory_count);
  el("summary").textContent =
    `${s.crc_present ? `CRC: ${s.crc_ok ? "OK" : "FAIL"}` : `${s.integrity_name}: OK`} · ` +
    `Деньги: ${s.money ?? "неизвестно"} · ` +
    `Предметов: ${s.inventory_count}`;
  const caps = s.capabilities ?? {};
  const supportedEdits = [
    caps.edit_money ? "деньги" : "деньги read-only",
    caps.edit_stacks ? "количество подтверждённых стаков" : "stack count read-only",
    caps.add_items && s.catalog_available ? "добавление из каталога" : "добавление read-only",
    caps.remove_items ? "удаление предметов" : "удаление read-only",
    caps.edit_durability ? "прочность оружия/экипировки (experimental)" : "прочность read-only",
    caps.edit_relations && s.faction_catalog_available ? "отношения с группировками (experimental)" : "отношения read-only",
    caps.edit_player_faction && s.faction_catalog_available && s.player_faction_editable ? "группировка игрока (experimental)" : "группировка игрока read-only",
  ];
  el("support").textContent =
    `Релиз: ${s.release_id} (${s.edition}). Формат: ${s.format_title}. ` +
    `Доступно: ${supportedEdits.join(", ")}; неизвестные поля остаются read-only.` +
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

  const addGroup = el("item-add-group");
  const addSelect = el("item-add-select");
  const catalogItems = s.catalog_items ?? [];
  addSelect.replaceChildren(...catalogItems.map((item) => {
    const option = document.createElement("option");
    option.value = item.key;
    option.textContent = item.name === item.key ? item.key : `${item.name} · ${item.key}`;
    return option;
  }));
  addGroup.disabled = !(caps.add_items && s.catalog_available && catalogItems.length);
  el("item-add-status").textContent = s.catalog_available
    ? `Доступно ключей: ${catalogItems.length}. Источник: ${s.catalog_source === "save-observed" ? "текущий сейв" : "официальный каталог"}.`
    : "Официальный каталог для браузера не найден в загруженном файле.";

  renderFaction(s);
  renderInventory();
  renderChanges();
}

function renderFaction(s) {
  const group = el("faction-group");
  const body = el("faction-relations").tBodies[0];
  const rows = s.faction_relations ?? [];
  const factions = (s.catalog_factions ?? []).filter((faction) => faction.numeric_id !== null && faction.numeric_id !== undefined);
  const caps = s.capabilities ?? {};
  const enabled = Boolean(caps.edit_relations && s.faction_catalog_available && s.faction_relations_editable && rows.length);
  const playerEnabled = Boolean(caps.edit_player_faction && s.faction_catalog_available && s.player_faction_editable && factions.length);
  group.disabled = !(enabled || playerEnabled);
  el("faction-status").textContent = enabled || playerEnabled
    ? `Загружено группировок: ${rows.length}; goodwill ${s.faction_goodwill_min ?? "?"}…${s.faction_goodwill_max ?? "?"}. Изменения staged, исходный сейв не изменён.`
    : s.faction_catalog_available
      ? "Relation registry или actor community не подтверждены; только чтение."
      : "Официальный faction catalog для этого релиза не найден.";
  const warning = el("faction-warning");
  warning.hidden = !(enabled || playerEnabled);

  const playerSelect = el("player-faction-select");
  playerSelect.replaceChildren(...factions.map((faction) => {
    const option = document.createElement("option");
    option.value = faction.key;
    option.textContent = faction.name === faction.key ? faction.key : `${faction.name} · ${faction.key}`;
    return option;
  }));
  const currentFaction = factions.find((faction) => faction.numeric_id === s.player_faction_index);
  el("player-faction-current").textContent = currentFaction
    ? (currentFaction.name === currentFaction.key ? currentFaction.key : `${currentFaction.name} · ${currentFaction.key}`)
    : s.player_faction_index === null || s.player_faction_index === undefined
      ? "неизвестно"
      : `community id ${s.player_faction_index} (нет в каталоге)`;
  const selectedPlayerFaction = state.playerFaction ?? currentFaction?.key ?? factions[0]?.key ?? "";
  playerSelect.value = selectedPlayerFaction;
  playerSelect.disabled = !playerEnabled;
  const playerStage = el("player-faction-stage");
  playerStage.disabled = !playerEnabled;
  playerStage.textContent = state.playerFaction === null ? "Застейджить" : "Группировка*";
  playerStage.onclick = () => {
    const key = playerSelect.value;
    if (!key) return;
    state.playerFaction = key === currentFaction?.key ? null : key;
    invalidate();
    renderFaction(state.snapshot);
    renderChanges();
    setStatus(`Принадлежность игрока ${key} подготовлена; исходный файл не изменён`);
  };
  body.replaceChildren(...rows.map((row) => {
    const tr = document.createElement("tr");
    const staged = state.relations.get(row.key);
    const current = row.stored ? Number(row.value) : 0;
    const name = document.createElement("td");
    name.textContent = row.name === row.key ? row.key : `${row.name} · ${row.key}`;
    name.title = `community id: ${row.numeric_id}`;
    tr.append(name);
    const currentCell = document.createElement("td");
    currentCell.textContent = row.stored ? String(row.value) : "0 (default)";
    tr.append(currentCell);
    const inputCell = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.min = String(s.faction_goodwill_min ?? -2147483648);
    input.max = String(s.faction_goodwill_max ?? 2147483647);
    input.step = "1";
    input.value = String(staged ?? current);
    inputCell.append(input);
    tr.append(inputCell);
    const actionCell = document.createElement("td");
    const button = document.createElement("button");
    button.className = "button";
    button.type = "button";
    button.textContent = staged === undefined ? "Застейджить" : "Отношение*";
    button.addEventListener("click", () => {
      const value = Number(input.value);
      const min = Number(s.faction_goodwill_min ?? -2147483648);
      const max = Number(s.faction_goodwill_max ?? 2147483647);
      if (!Number.isInteger(value) || value < min || value > max) {
        setStatus(`Goodwill должен быть целым числом ${min}…${max}`, "error");
        return;
      }
      if (value === current) state.relations.delete(row.key);
      else state.relations.set(row.key, value);
      invalidate();
      renderFaction(state.snapshot);
      renderChanges();
      setStatus(`Отношение ${row.key} подготовлено; исходный файл не изменён`);
    });
    actionCell.append(button);
    tr.append(actionCell);
    return tr;
  }));
}

function visibleItems() {
  const query = el("inventory-search").value.trim().toLowerCase();
  const filter = el("inventory-filter").value;
  return (state.snapshot?.inventory ?? []).filter((item) => {
    if (filter === "editable" && !item.editable) return false;
    if (filter === "readonly" && item.editable) return false;
    if (
      filter === "staged" &&
      !state.stacks.has(item.handle) &&
      !state.durability.has(item.handle) &&
      !state.detach.has(item.handle)
    ) return false;
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
    const stagedDurability = state.durability.get(item.handle);
    tr.className = state.detach.has(item.handle)
      ? "staged"
      : staged !== undefined || stagedDurability !== undefined ? "staged" : item.editable ? "" : "readonly";
    for (const cell of [
      item.name, item.category, item.position, item.size_text, item.type_key,
      item.count === null ? "неизвестно" : String(item.count),
      item.total_weight === null ? "неизвестно" : item.total_weight.toFixed(3),
    ]) {
      const td = document.createElement("td");
      td.textContent = cell;
      tr.append(td);
    }
    const conditionTd = document.createElement("td");
    if (item.condition === null || item.condition === undefined) {
      conditionTd.textContent = "неизвестно";
    } else if (item.condition_editable && state.snapshot.capabilities?.edit_durability) {
      const input = document.createElement("input");
      input.className = "condition-input";
      input.type = "number";
      input.min = "0";
      input.max = "100";
      input.step = "0.1";
      input.value = String(((stagedDurability ?? item.condition) * 100).toFixed(1));
      input.title = "Экспериментально: STATE/UPDATE/client-data mirrors; исходный файл не меняется до preview";
      input.addEventListener("change", () => {
        const value = Number(input.value);
        if (!Number.isFinite(value) || value < 0 || value > 100) {
          input.value = String((item.condition * 100).toFixed(1));
          return;
        }
        const normalized = value / 100;
        if (Math.abs(normalized - item.condition) <= 0.000001) state.durability.delete(item.handle);
        else state.durability.set(item.handle, normalized);
        invalidate();
        renderInventory();
        renderChanges();
      });
      conditionTd.append(input);
    } else {
      conditionTd.textContent = `${(item.condition * 100).toFixed(1)}%`;
      conditionTd.className = "muted";
    }
    tr.append(conditionTd);
    const handleTd = document.createElement("td");
    handleTd.textContent = item.handle_hex;
    tr.append(handleTd);
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
    } else if (!state.snapshot.capabilities?.edit_stacks) {
      td.textContent = "только чтение";
      td.className = "muted";
    }
    if (state.snapshot.capabilities?.remove_items) {
      const remove = document.createElement("button");
      remove.className = "button";
      remove.type = "button";
      remove.textContent = state.detach.has(item.handle) ? "Отменить" : "Удалить";
      remove.addEventListener("click", () => {
        if (state.detach.has(item.handle)) state.detach.delete(item.handle);
        else {
          state.detach.add(item.handle);
          state.stacks.delete(item.handle);
          state.durability.delete(item.handle);
        }
        invalidate();
        renderInventory();
        renderChanges();
      });
      td.append(document.createTextNode(" "));
      td.append(remove);
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
  for (const [handle, condition] of state.durability) {
    const item = state.snapshot.inventory.find((i) => i.handle === handle);
    items.push(`Прочность ${item?.handle_hex ?? `0x${handle.toString(16).padStart(8, "0")}`}: ${(item.condition * 100).toFixed(1)}% → ${(condition * 100).toFixed(1)}% (experimental)`);
  }
  for (const [key, goodwill] of state.relations) {
    const row = (state.snapshot.faction_relations ?? []).find((item) => item.key === key);
    const before = row?.stored ? row.value : 0;
    items.push(`С риском: отношение ${key}: ${before} → ${goodwill}; backup обязателен`);
  }
  if (state.playerFaction !== null) {
    const current = (state.snapshot.catalog_factions ?? []).find(
      (faction) => faction.numeric_id === state.snapshot.player_faction_index,
    );
    const target = (state.snapshot.catalog_factions ?? []).find(
      (faction) => faction.key === state.playerFaction,
    );
    const label = (faction, fallback) => faction
      ? (faction.name === faction.key ? faction.key : `${faction.name} · ${faction.key}`)
      : fallback;
    items.push(`ОПАСНО: группировка игрока ${label(current, "неизвестно")} → ${label(target, state.playerFaction)}; сюжет может перезаписать; backup обязателен`);
  }
  for (const [key, quantity] of state.adds) {
    items.push(`ОПАСНО: добавить ${key} × ${quantity}; backup обязателен`);
  }
  for (const handle of state.detach) {
    const item = state.snapshot.inventory.find((i) => i.handle === handle);
    items.push(`ОПАСНО: удалить ${item?.handle_hex ?? `0x${handle.toString(16).padStart(8, "0")}`}; backup обязателен`);
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
    const adds = JSON.stringify([...state.adds.entries()]);
    const detach = JSON.stringify([...state.detach].map((handle) => [handle, true]));
    const durability = JSON.stringify([...state.durability.entries()]);
    const relations = JSON.stringify([...state.relations.entries()]);
    const playerFaction = JSON.stringify(state.playerFaction);
    const result = JSON.parse(state.bridge.prepare(state.money, stacks, adds, detach, durability, relations, playerFaction));
    state.prepared = result;

    const lines = [`Копия готова: ${result.size_text}, SHA ${result.output_sha256.slice(0, 12)}…`];
    if (result.money[0] !== result.money[1]) {
      lines.push(`деньги ${result.money[0]} → ${result.money[1]}`);
    }
    for (const [handle, before, after] of result.stacks) {
      lines.push(`${handle}: ${before} → ${after}`);
    }
    for (const [, key, count] of result.adds ?? []) {
      lines.push(`добавлен ${key} (${count ?? "без count"})`);
    }
    for (const handle of result.removed ?? []) {
      lines.push(`удалён ${handle}`);
    }
    for (const [handle, before, after] of result.durability ?? []) {
      lines.push(`прочность ${handle}: ${before === null ? "?" : `${(before * 100).toFixed(1)}%`} → ${after === null ? "?" : `${(after * 100).toFixed(1)}%`}`);
    }
    for (const [key, before, after] of result.faction_relations ?? []) {
      lines.push(`отношение ${key}: ${before ?? 0} → ${after ?? "?"} (experimental)`);
    }
    if (result.player_faction?.[0] !== result.player_faction?.[1]) {
      lines.push(`группировка игрока: ${result.player_faction[0] ?? "?"} → ${result.player_faction[1] ?? "?"} (experimental)`);
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
el("item-add-stage").addEventListener("click", () => {
  const key = el("item-add-select").value;
  const quantity = Number(el("item-add-quantity").value);
  const definition = (state.snapshot?.catalog_items ?? []).find((item) => item.key === key);
  const max = Number(definition?.max_stack ?? 65535);
  if (!key || !Number.isInteger(quantity) || quantity < 1 || quantity > max) {
    setStatus(`Количество должно быть целым числом 1…${max}`, "error");
    return;
  }
  state.adds.set(key, quantity);
  invalidate();
  renderChanges();
  setStatus(`Добавление ${key} × ${quantity} подготовлено; исходный файл не изменён`);
});
el("preview").addEventListener("click", preview);
el("download").addEventListener("click", download);

el("file-input").disabled = true;
boot().catch(fail);
