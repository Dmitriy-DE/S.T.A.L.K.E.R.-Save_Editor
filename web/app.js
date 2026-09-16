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
  adds: new Map(),
  upgrades: new Map(),
  durability: new Map(),
  factionRelations: new Map(),
  playerFaction: null,
  selectedUpgradeHandle: null,
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

function copySupportFallback(value) {
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  let copied = false;
  try {
    copied = typeof document.execCommand === "function" && document.execCommand("copy");
  } finally {
    textarea.remove();
  }
  if (!copied) throw new Error("Не удалось скопировать значение");
}

async function copySupportValue(value) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch (_error) {
      // Fall back for local files and browsers that deny clipboard permission.
    }
  }
  copySupportFallback(value);
}

function installSupportUi() {
  const modal = el("support-modal");
  const openButton = el("support-button");
  const closeButton = el("support-close");
  if (!modal || !openButton || !closeButton) return;

  const close = () => {
    modal.hidden = true;
    document.body.classList.remove("modal-open");
  };
  openButton.addEventListener("click", () => {
    modal.hidden = false;
    document.body.classList.add("modal-open");
    closeButton.focus();
  });
  closeButton.addEventListener("click", close);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) close();
  });

  for (const button of document.querySelectorAll(".support-copy")) {
    button.addEventListener("click", async () => {
      try {
        await copySupportValue(button.dataset.copy || "");
        button.textContent = "Copied";
        button.classList.add("copied");
        window.clearTimeout(button.copyTimer);
        button.copyTimer = window.setTimeout(() => {
          button.textContent = "Copy";
          button.classList.remove("copied");
        }, 1200);
      } catch (error) {
        setStatus(error, "error");
      }
    });
  }
}

installSupportUi();

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
    state.adds.clear();
    state.upgrades.clear();
    state.durability.clear();
    state.factionRelations.clear();
    state.playerFaction = null;
    state.selectedUpgradeHandle = null;
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
  const experimental = new Set(caps.experimental_fields ?? []);
  const editLabel = (field, text) =>
    experimental.has(field) ? `Экспериментально: ${text}` : text;
  const riskLabel = (field, text) => {
    if (["add_items", "remove_items", "edit_player_faction"].includes(field)) {
      return `ОПАСНО: ${text}`;
    }
    if (field === "edit_relations") return `С риском: ${text}`;
    return editLabel(field, text);
  };
  const supportedEdits = [
    caps.edit_money ? editLabel("edit_money", "деньги") : "деньги read-only",
    caps.edit_stacks ? editLabel("edit_stacks", "количество подтверждённых стаков") : "stack count read-only",
    caps.add_items && s.catalog_available ? riskLabel("add_items", "добавление из каталога") : "добавление read-only",
    caps.remove_items ? riskLabel("remove_items", "удаление предметов") : "удаление read-only",
    caps.edit_durability ? editLabel("edit_durability", "прочность оружия/экипировки") : "прочность read-only",
    caps.edit_upgrades ? editLabel("edit_upgrades", "апгрейды ЧН/ЗП") : "апгрейды read-only",
    caps.edit_relations ? riskLabel("edit_relations", "отношения группировок") : "отношения read-only",
    caps.edit_player_faction ? riskLabel("edit_player_faction", "принадлежность игрока") : "принадлежность read-only",
  ];
  const experimentalWarning = experimental.size
    ? " Экспериментальные поля: перед проверкой сохрани резервную копию; браузер исходник не перезаписывает."
    : "";
  el("support").textContent =
    `Релиз: ${s.release_id} (${s.edition}). Формат: ${s.format_title}. ` +
    `Доступно: ${supportedEdits.join(", ")}; неизвестные поля остаются read-only.` +
    experimentalWarning +
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

  renderFactionEditor();

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
    ? `${experimental.has("add_items") ? "Экспериментально: " : ""}Доступно ключей: ${catalogItems.length}. Источник: ${s.catalog_source === "save-observed" ? "текущий сейв" : "официальный каталог"}.`
    : "Официальный каталог для браузера не найден в загруженном файле.";

  const upgradeItems = (s.inventory ?? []).filter(canShowUpgradeEditor);
  const upgradeGroup = el("upgrade-group");
  const upgradeSelect = el("upgrade-item-select");
  upgradeSelect.replaceChildren(...upgradeItems.map((item) => {
    const option = document.createElement("option");
    option.value = String(item.handle);
    option.textContent = `${item.name || "Неизвестный объект"} · ${item.type_key} · ${item.handle_hex}`;
    return option;
  }));
  const upgradeAllowed = Boolean(caps.edit_upgrades && upgradeItems.length);
  upgradeGroup.disabled = !upgradeAllowed;
  el("upgrade-status").textContent = upgradeAllowed
    ? `${experimental.has("edit_upgrades") ? "Экспериментально: " : ""}` +
      (s.upgrade_catalog_available
        ? `Доступно официальных апгрейдов: ${(s.catalog_upgrades ?? []).length}. Выбор staged; bytes пока не изменены.`
        : "Официальный каталог апгрейдов не найден: добавление read-only, очистка уже записанного вектора доступна.")
    : (caps.edit_upgrades
      ? "В этом сейве нет подтверждённых upgrade vectors."
      : "Для выбранного релиза правка апгрейдов остаётся read-only.");
  if (upgradeItems.length) {
    const selected = upgradeItems.some((item) => item.handle === state.selectedUpgradeHandle)
      ? state.selectedUpgradeHandle
      : upgradeItems[0].handle;
    state.selectedUpgradeHandle = selected;
    upgradeSelect.value = String(selected);
  }

  renderInventory();
  renderUpgradeEditor();
  renderChanges();
}

function renderFactionEditor() {
  const s = state.snapshot;
  const statusLabel = el("faction-status");
  const currentLabel = el("player-faction-current");
  const select = el("player-faction-select");
  const stagePlayer = el("player-faction-stage");
  const warning = el("faction-warning");
  const body = el("faction-relations")?.tBodies[0];
  if (!s || !statusLabel || !currentLabel || !select || !stagePlayer || !body) return;

  const caps = s.capabilities ?? {};
  const experimental = new Set(caps.experimental_fields ?? []);
  const catalog = s.catalog_factions ?? [];
  const rows = s.faction_relations ?? [];
  const currentKey = s.player_faction_key ?? "";
  const currentText = currentKey
    ? `${currentKey}${s.player_faction_index === null || s.player_faction_index === undefined ? "" : ` · #${s.player_faction_index}`}`
    : s.player_faction_index === null || s.player_faction_index === undefined
      ? "неизвестно"
      : `неизвестно · #${s.player_faction_index}`;
  currentLabel.textContent = state.playerFaction ?? currentText;

  select.replaceChildren(...catalog
    .filter((faction) => faction.numeric_id !== null && faction.numeric_id !== undefined)
    .map((faction) => {
      const option = document.createElement("option");
      option.value = faction.key;
      option.textContent = faction.name === faction.key
        ? faction.key
        : `${faction.name} · ${faction.key}`;
      return option;
    }));
  if (state.playerFaction ?? currentKey) {
    select.value = state.playerFaction ?? currentKey;
  }
  const playerAllowed = Boolean(
    caps.edit_player_faction && catalog.length && select.options.length
  );
  select.disabled = !playerAllowed;
  stagePlayer.disabled = !playerAllowed;
  stagePlayer.textContent = state.playerFaction ? "Группировка*" : "Застейджить";

  const goodwillMin = s.faction_goodwill_min;
  const goodwillMax = s.faction_goodwill_max;
  const relationAllowed = Boolean(
    caps.edit_relations && goodwillMin !== null && goodwillMin !== undefined &&
    goodwillMax !== null && goodwillMax !== undefined
  );
  statusLabel.textContent = catalog.length
    ? `${catalog.length} группировок из официального каталога; ` +
      (relationAllowed
        ? `${experimental.has("edit_relations") ? "Экспериментально: " : ""}goodwill ${goodwillMin}…${goodwillMax}; перед записью нужен backup`
        : "изменения read-only до игрового evidence")
    : "Официальный faction catalog для этого релиза недоступен.";

  if (s.release_id === "stalker-cs") {
    warning.hidden = false;
    warning.textContent = "ЧН: принадлежность Шрама может быть перезаписана сюжетным скриптом до нужной миссии; редактор квесты не моделирует.";
  } else if (s.release_id === "stalker-soc" || s.release_id === "stalker-cop") {
    warning.hidden = false;
    warning.textContent = "Поле community участвует в расчёте отношений; сюжетный скрипт может перезаписать его после загрузки. Условия этого сейва не подтверждены.";
  } else {
    warning.hidden = true;
    warning.textContent = "";
  }
  if (experimental.has("edit_relations") || experimental.has("edit_player_faction")) {
    warning.hidden = false;
    warning.textContent = `${warning.textContent ? `${warning.textContent} ` : ""}Экспериментально: перед проверкой сделай backup; браузер исходный файл не изменяет.`;
  }

  if (!rows.length) {
    body.replaceChildren(Object.assign(document.createElement("tr"), {
      innerHTML: '<td colspan="4" class="muted">Relation registry или официальный каталог недоступен.</td>',
    }));
    return;
  }
  body.replaceChildren(...rows.map((row) => {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = row.name === row.key ? row.key : `${row.name} · ${row.key}`;
    const current = document.createElement("td");
    current.textContent = row.stored ? String(row.value) : `${row.value} (default)`;
    const next = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.min = goodwillMin === null || goodwillMin === undefined ? "" : String(goodwillMin);
    input.max = goodwillMax === null || goodwillMax === undefined ? "" : String(goodwillMax);
    input.step = "1";
    input.value = String(state.factionRelations.get(row.key) ?? row.value);
    input.disabled = !relationAllowed || row.numeric_id === null || row.numeric_id === undefined;
    next.append(input);
    const actions = document.createElement("td");
    const button = document.createElement("button");
    button.className = "button";
    button.type = "button";
    button.textContent = state.factionRelations.has(row.key) ? "Отношение*" : "Застейджить";
    button.disabled = input.disabled;
    button.addEventListener("click", () => {
      const value = Number(input.value);
      if (!Number.isInteger(value) || value < Number(goodwillMin) || value > Number(goodwillMax)) {
        setStatus(`Goodwill должен быть целым числом ${goodwillMin}…${goodwillMax}`, "error");
        return;
      }
      if (value === row.value) state.factionRelations.delete(row.key);
      else state.factionRelations.set(row.key, value);
      invalidate();
      renderFactionEditor();
      renderChanges();
      setStatus(`Отношение ${row.key} подготовлено; исходный файл не изменён`);
    });
    actions.append(button);
    tr.append(name, current, next, actions);
    return tr;
  }));
}

function selectedUpgradeItem() {
  const handle = state.selectedUpgradeHandle;
  return (state.snapshot?.inventory ?? []).find((item) => item.handle === handle) ?? null;
}

function canShowUpgradeEditor(item) {
  if (!item?.upgrade_editable) return false;
  if ((item.upgrades ?? []).length) return true;
  return (state.snapshot?.catalog_upgrades ?? []).some((upgrade) =>
    (upgrade.applicable_item_keys ?? []).includes(item.type_key)
  );
}

function iconCategory(item) {
  const category = String(item.category ?? "").toLowerCase();
  if (category.includes("weapon") || category.includes("оруж")) return "weapon";
  if (category.includes("ammo") || category.includes("патрон")) return "ammo";
  if (category.includes("outfit") || category.includes("брон") || category.includes("экип")) return "outfit";
  if (category.includes("artifact") || category.includes("артеф")) return "artifact";
  if (category.includes("consum") || category.includes("расход")) return "consumable";
  if (category.includes("gren") || category.includes("гранат")) return "grenade";
  return "item";
}

function renderUpgradeEditor() {
  const item = selectedUpgradeItem();
  const options = el("upgrade-options");
  const stage = el("upgrade-stage");
  const clear = el("upgrade-clear");
  options.replaceChildren();
  stage.disabled = true;
  clear.disabled = true;
  if (!item || !state.snapshot?.capabilities?.edit_upgrades || !item.upgrade_editable) {
    return;
  }

  const definitions = (state.snapshot.catalog_upgrades ?? []).filter((upgrade) =>
    (upgrade.applicable_item_keys ?? []).includes(item.type_key)
  );
  const current = [...(item.upgrades ?? [])];
  const effective = state.upgrades.has(item.handle)
    ? [...state.upgrades.get(item.handle)]
    : current;
  const definitionKeys = new Set(definitions.map((upgrade) => upgrade.key));
  const unknown = [...new Set(effective.filter((key) => !definitionKeys.has(key)))];

  for (const key of unknown) {
    const label = document.createElement("label");
    label.className = "upgrade-option unknown";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = true;
    input.disabled = true;
    input.dataset.upgradeKey = key;
    label.append(input, document.createTextNode(`Неизвестный upgrade · ${key}`));
    options.append(label);
  }
  for (const upgrade of definitions) {
    const label = document.createElement("label");
    label.className = "upgrade-option";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = effective.includes(upgrade.key);
    input.dataset.upgradeKey = upgrade.key;
    const name = upgrade.name && upgrade.name !== upgrade.key
      ? `${upgrade.name} · ${upgrade.key}`
      : upgrade.key;
    const property = upgrade.property ? ` [${upgrade.property}]` : "";
    label.append(input, document.createTextNode(`${name}${property}`));
    options.append(label);
  }

  const catalogStatus = state.snapshot.upgrade_catalog_available
    ? `Текущие: ${current.length} · доступные для ${item.type_key}: ${definitions.length}`
    : `Текущие: ${current.length} · каталог добавления недоступен`;
  const upgradePrefix = state.snapshot.capabilities?.experimental_fields?.includes("edit_upgrades")
    ? "Экспериментально: "
    : "";
  el("upgrade-status").textContent = `${upgradePrefix}${catalogStatus}; bytes пока не изменены.`;
  stage.disabled = !definitions.length && !effective.length;
  clear.disabled = !effective.length;
}

function stageSelectedUpgrades() {
  const item = selectedUpgradeItem();
  if (!item || !item.upgrade_editable || !state.snapshot?.capabilities?.edit_upgrades) return;
  const values = [...el("upgrade-options").querySelectorAll("input[data-upgrade-key]:checked")]
    .map((input) => input.dataset.upgradeKey)
    .filter(Boolean);
  const current = item.upgrades ?? [];
  if (values.length === current.length && values.every((value, index) => value === current[index])) {
    state.upgrades.delete(item.handle);
  } else {
    state.upgrades.set(item.handle, values);
  }
  invalidate();
  renderInventory();
  renderUpgradeEditor();
  renderChanges();
  setStatus(`Апгрейды ${item.type_key} подготовлены; исходный файл не изменён`);
}

function clearSelectedUpgrades() {
  const item = selectedUpgradeItem();
  if (!item || !item.upgrade_editable || !state.snapshot?.capabilities?.edit_upgrades) return;
  if ((item.upgrades ?? []).length === 0) {
    state.upgrades.delete(item.handle);
  } else {
    state.upgrades.set(item.handle, []);
  }
  invalidate();
  renderInventory();
  renderUpgradeEditor();
  renderChanges();
  setStatus(`Апгрейды ${item.type_key} будут очищены; исходный файл не изменён`);
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
      !state.upgrades.has(item.handle) &&
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
    const upgradesStaged = state.upgrades.has(item.handle);
    const durabilityStaged = state.durability.has(item.handle);
    tr.className = state.detach.has(item.handle)
      ? "staged"
      : staged !== undefined || upgradesStaged || durabilityStaged
        ? "staged"
        : item.editable ? "" : "readonly";
    const iconCell = document.createElement("td");
    const icon = document.createElement("span");
    icon.className = `item-icon item-icon-${iconCategory(item)}`;
    icon.title = item.icon_x !== null && item.icon_x !== undefined
      ? `Официальный atlas: ${item.icon_x},${item.icon_y}`
      : "Категорийный знак; официальный atlas недоступен в браузере";
    iconCell.append(icon);
    tr.append(iconCell);
    for (const cell of [
      item.name, item.category, item.position, item.size_text, item.type_key,
      item.count === null ? "неизвестно" : String(item.count),
      item.total_weight === null ? "неизвестно" : item.total_weight.toFixed(3),
      item.condition === null || item.condition === undefined
        ? "неизвестно"
        : `${(item.condition * 100).toFixed(1)}%${durabilityStaged ? ` → ${(state.durability.get(item.handle) * 100).toFixed(1)}%` : ""}`,
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
    } else if (!state.snapshot.capabilities?.edit_stacks) {
      td.textContent = "только чтение";
      td.className = "muted";
    }
    if (item.condition_editable && state.snapshot.capabilities?.edit_durability) {
      const conditionAction = document.createElement("div");
      conditionAction.className = "condition-action";
      const conditionInput = document.createElement("input");
      conditionInput.className = "condition-input";
      conditionInput.type = "number";
      conditionInput.min = "0";
      conditionInput.max = "100";
      conditionInput.step = "1";
      conditionInput.value = String(
        ((state.durability.get(item.handle) ?? item.condition) * 100).toFixed(1)
      );
      conditionInput.setAttribute("aria-label", `Прочность ${item.type_key}`);
      const conditionStage = document.createElement("button");
      conditionStage.className = "button";
      conditionStage.type = "button";
      conditionStage.textContent = durabilityStaged ? "Прочность*" : "Прочность";
      if (state.snapshot.capabilities?.experimental_fields?.includes("edit_durability")) {
        conditionStage.title = "Экспериментально: перед записью нужен backup";
      }
      conditionStage.addEventListener("click", () => {
        const value = Number(conditionInput.value);
        if (!Number.isFinite(value) || value < 0 || value > 100) {
          conditionInput.value = String((item.condition * 100).toFixed(1));
          setStatus("Прочность должна быть в диапазоне 0…100%", "error");
          return;
        }
        const normalized = value / 100;
        if (Math.abs(normalized - item.condition) <= 1e-6) {
          state.durability.delete(item.handle);
        } else {
          state.durability.set(item.handle, normalized);
        }
        invalidate();
        renderInventory();
        renderChanges();
        setStatus(`Прочность ${item.type_key} подготовлена; исходный файл не изменён`);
      });
      conditionAction.append(conditionInput, conditionStage);
      td.append(document.createElement("br"), conditionAction);
    } else if (
      item.condition !== null
      && item.condition !== undefined
      && !state.snapshot.capabilities?.edit_durability
    ) {
      const conditionNote = document.createElement("div");
      conditionNote.className = "muted condition-action";
      conditionNote.textContent = "прочность: только чтение";
      td.append(conditionNote);
    }
    if (state.snapshot.capabilities?.edit_upgrades && canShowUpgradeEditor(item)) {
      const upgrade = document.createElement("button");
      upgrade.className = "button";
      upgrade.type = "button";
      upgrade.textContent = upgradesStaged ? "Апгрейды*" : "Апгрейды";
      upgrade.addEventListener("click", () => {
        state.selectedUpgradeHandle = item.handle;
        el("upgrade-item-select").value = String(item.handle);
        renderUpgradeEditor();
        el("upgrade-group").scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
      td.append(upgrade);
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
  const experimental = new Set(state.snapshot?.capabilities?.experimental_fields ?? []);
  const editLabel = (field, text) =>
    experimental.has(field) ? `Экспериментально: ${text}` : text;
  const riskLabel = (field, text) => {
    if (["add_items", "remove_items", "edit_player_faction"].includes(field)) {
      return `ОПАСНО: ${text}`;
    }
    if (field === "edit_relations") return `С риском: ${text}`;
    return editLabel(field, text);
  };
  if (state.money !== null) {
    items.push(`Деньги: ${state.snapshot.money} → ${state.money}`);
  }
  for (const [handle, count] of state.stacks) {
    const item = state.snapshot.inventory.find((i) => i.handle === handle);
    items.push(`Стак ${item.handle_hex}: ${item.count} → ${count}`);
  }
  for (const [key, quantity] of state.adds) {
    items.push(riskLabel("add_items", `Добавить ${key} × ${quantity}`));
  }
  for (const [handle, upgrades] of state.upgrades) {
    const item = state.snapshot.inventory.find((i) => i.handle === handle);
    const before = item?.upgrades ?? [];
    items.push(
      riskLabel(
        "edit_upgrades",
        `Апгрейды ${item?.handle_hex ?? `0x${handle.toString(16).padStart(8, "0")}`}: ` +
        `${before.join(", ") || "нет"} → ${upgrades.join(", ") || "нет"}`,
      ),
    );
  }
  for (const [handle, condition] of state.durability) {
    const item = state.snapshot.inventory.find((i) => i.handle === handle);
    const before = item?.condition === null || item?.condition === undefined
      ? "unknown"
      : `${(item.condition * 100).toFixed(1)}%`;
    items.push(
      riskLabel(
        "edit_durability",
        `Прочность ${item?.handle_hex ?? `0x${handle.toString(16).padStart(8, "0")}`}: ` +
        `${before} → ${(condition * 100).toFixed(1)}%`,
      ),
    );
  }
  for (const handle of state.detach) {
    const item = state.snapshot.inventory.find((i) => i.handle === handle);
    items.push(
      riskLabel(
        "remove_items",
        `Удалить ${item?.handle_hex ?? `0x${handle.toString(16).padStart(8, "0")}`}`,
      ),
    );
  }
  for (const [key, value] of state.factionRelations) {
    const row = (state.snapshot.faction_relations ?? []).find((entry) => entry.key === key);
    items.push(
      riskLabel(
        "edit_relations",
        `Отношение ${key}: ${row?.value ?? "unknown"} → ${value}`,
      ),
    );
  }
  if (state.playerFaction !== null) {
    const before = state.snapshot.player_faction_key ?? (
      state.snapshot.player_faction_index === null || state.snapshot.player_faction_index === undefined
        ? "unknown"
        : `#${state.snapshot.player_faction_index}`
    );
    items.push(
      riskLabel(
        "edit_player_faction",
        `Группировка игрока: ${before} → ${state.playerFaction}`,
      ),
    );
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
    const upgrades = JSON.stringify([...state.upgrades.entries()]);
    const durability = JSON.stringify([...state.durability.entries()]);
    const relations = JSON.stringify([...state.factionRelations.entries()]);
    const result = JSON.parse(
      state.bridge.prepare(
        state.money,
        stacks,
        adds,
        detach,
        upgrades,
        durability,
        relations,
        state.playerFaction,
      )
    );
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
    for (const [handle, before, after] of result.upgrades ?? []) {
      lines.push(`апгрейды ${handle}: ${before.join(", ") || "нет"} → ${after.join(", ") || "нет"}`);
    }
    for (const [handle, before, after] of result.durability ?? []) {
      const beforeText = before === null ? "unknown" : `${(before * 100).toFixed(1)}%`;
      const afterText = after === null ? "unknown" : `${(after * 100).toFixed(1)}%`;
      lines.push(`прочность ${handle}: ${beforeText} → ${afterText}`);
    }
    for (const [key, before, after] of result.faction_relations ?? []) {
      lines.push(`отношение ${key}: ${before ?? "unknown"} → ${after ?? "unknown"}`);
    }
    if (result.player_faction && result.player_faction[0] !== result.player_faction[1]) {
      lines.push(`группировка игрока: ${result.player_faction[0] ?? "unknown"} → ${result.player_faction[1] ?? "unknown"}`);
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
el("player-faction-stage").addEventListener("click", () => {
  const selected = el("player-faction-select").value;
  if (!selected || !state.snapshot?.capabilities?.edit_player_faction) return;
  state.playerFaction = selected === state.snapshot.player_faction_key ? null : selected;
  invalidate();
  renderFactionEditor();
  renderChanges();
  setStatus(`Группировка игрока ${selected} подготовлена; исходный файл не изменён`);
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
el("upgrade-item-select").addEventListener("change", (event) => {
  const value = Number(event.target.value);
  state.selectedUpgradeHandle = Number.isSafeInteger(value) ? value : null;
  renderUpgradeEditor();
});
el("upgrade-stage").addEventListener("click", stageSelectedUpgrades);
el("upgrade-clear").addEventListener("click", clearSelectedUpgrades);
el("preview").addEventListener("click", preview);
el("download").addEventListener("click", download);

el("file-input").disabled = true;
boot().catch(fail);
