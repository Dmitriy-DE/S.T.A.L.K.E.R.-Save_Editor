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
  upgrades: new Map(),
  placements: new Map(),
  relations: new Map(),
  playerFaction: null,
  adds: new Map(),
  detach: new Set(),
  equipmentSelectedHandle: null,
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
    state.upgrades.clear();
    state.placements.clear();
    state.relations.clear();
    state.playerFaction = null;
    state.adds.clear();
    state.detach.clear();
    state.equipmentSelectedHandle = null;
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

  el("card-location").textContent = s.level_name ?? "не разобрано";
  el("card-time").textContent = s.game_time === null ? "не разобрано" : String(s.game_time);
  el("card-money").textContent = s.money === null ? "неизвестно" : String(s.money);
  el("card-items").textContent = String(s.inventory_count);
  el("summary").textContent =
    `${s.crc_present ? `CRC: ${s.crc_ok ? "OK" : "FAIL"}` : `${s.integrity_name}: OK`} · ` +
    `Деньги: ${s.money ?? "неизвестно"} · ` +
    `Предметов: ${s.inventory_count}`;
  const caps = s.capabilities ?? {};
  const supportedEdits = [
    caps.edit_money
      ? (caps.experimental_fields?.includes("edit_money")
        ? "деньги (experimental)"
        : "деньги")
      : "деньги read-only",
    caps.edit_stacks ? "количество подтверждённых стаков" : "stack count read-only",
    caps.add_items && s.catalog_available ? "добавление из каталога" : "добавление read-only",
    caps.remove_items ? "удаление предметов" : "удаление read-only",
    caps.edit_durability ? "прочность подтверждённой брони (experimental)" : "прочность read-only",
    caps.edit_upgrades && s.upgrade_catalog_available ? "улучшения оружия/экипировки (experimental)" : "улучшения read-only",
    caps.edit_placement ? "размещение предметов (experimental)" : "размещение read-only",
    caps.edit_relations && s.faction_catalog_available ? "отношения с группировками (experimental)" : "отношения read-only",
    caps.edit_player_faction && s.faction_catalog_available && s.player_faction_editable ? "группировка игрока (experimental)" : "группировка игрока read-only",
  ];
  const equipment = caps.equipment ?? {};
  if (equipment.durability) {
    supportedEdits.push(`оборудование: прочность ${equipment.durability.maturity}`);
    supportedEdits.push(`улучшения ${equipment.upgrades?.maturity ?? "unsupported"}`);
  }
  el("support").textContent =
    `Релиз: ${s.release_id} (${s.edition}). Формат: ${s.format_title}. ` +
    `Доступно: ${supportedEdits.join(", ")}; неизвестные поля остаются read-only.` +
    (s.warnings.length ? ` Предупреждения: ${s.warnings.join(" ")}` : "") +
    (caps.experimental_fields?.includes("edit_money")
      ? " Изменение денег экспериментальное: загрузка и пересохранение игрой не подтверждены."
      : "");

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
    ? `${s.money} → ${s.money}${caps.experimental_fields?.includes("edit_money") ? " • экспериментально" : ""}`
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

  const helmetOption = [...el("equipment-filter").options]
    .find((option) => option.value === "helmet");
  const helmetSupported = s.helmet_category_supported === true;
  if (helmetOption) {
    helmetOption.hidden = !helmetSupported;
    helmetOption.disabled = !helmetSupported;
    if (!helmetSupported && el("equipment-filter").value === "helmet") {
      el("equipment-filter").value = "all";
    }
  }
  el("equipment-repair-helmet").hidden = !helmetSupported;

  renderFaction(s);
  renderInventory();
  renderEquipment();
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
      !state.upgrades.has(item.handle) &&
      !state.placements.has(item.handle) &&
      !state.detach.has(item.handle)
    ) return false;
    if (!query) return true;
    return [item.name, item.category, item.type_key, item.handle_hex]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

const ITEM_GLYPH_CATEGORIES = new Set([
  "weapon",
  "ammo",
  "outfit",
  "artifact",
  "consumable",
  "grenade",
  "item",
]);

function itemGlyphCategory(category) {
  const value = String(category ?? "").toLowerCase();
  if (value.includes("оруж") || value.includes("weapon")) return "weapon";
  if (value.includes("патрон") || value.includes("ammo")) return "ammo";
  if (value.includes("брон") || value.includes("экип") || value.includes("outfit")) return "outfit";
  if (value.includes("артеф") || value.includes("artifact")) return "artifact";
  if (value.includes("гранат") || value.includes("grenade")) return "grenade";
  if (value.includes("расход") || value.includes("consum")) return "consumable";
  return ITEM_GLYPH_CATEGORIES.has(value) ? value : "item";
}

function itemCategoryGlyph(item) {
  const category = itemGlyphCategory(item.category);
  const glyph = document.createElement("span");
  glyph.className = `zone-item-glyph zone-item-glyph-${category}`;
  const label = `Категория предмета: ${item.category || "неизвестно"}`;
  glyph.setAttribute("role", "img");
  glyph.setAttribute("aria-label", label);
  glyph.title = item.icon_x === null || item.icon_x === undefined
    ? label
    : `${label}; официальный atlas ${item.icon_texture ?? "ui_icon_equipment"} [${item.icon_x}, ${item.icon_y}]`;
  return glyph;
}

function itemGlyph(item) {
  // Prefer the shipped icon pack by save key, then by an exact catalog display
  // name. The latter is needed for S2 saves whose opaque type key resolves to
  // an official prototype name only after parsing the embedded name table.
  const candidates = [item.type_key, item.name].filter(Boolean);
  if (!candidates.length) {
    return itemCategoryGlyph(item);
  }
  const img = document.createElement("img");
  img.className = "zone-item-icon";
  img.loading = "lazy";
  img.decoding = "async";
  let candidateIndex = 0;
  const setSource = () => {
    const candidate = candidates[candidateIndex];
    img.alt = `Иконка: ${candidate}`;
    img.title = candidate;
    img.src = `icons/${encodeURIComponent(candidate)}.png`;
  };
  img.addEventListener("error", () => {
    candidateIndex += 1;
    if (candidateIndex < candidates.length) {
      setSource();
      return;
    }
    img.replaceWith(itemCategoryGlyph(item));
  });
  setSource();
  return img;
}

function upgradeDefinitionsFor(item) {
  return (state.snapshot?.catalog_upgrades ?? []).filter((upgrade) =>
    (upgrade.applicable_item_keys ?? []).includes(item.type_key) ||
    upgrade.item_key === item.type_key,
  );
}

function renderUpgradeEditor(item, cell) {
  if (!Array.isArray(item.upgrades)) {
    cell.textContent = "только чтение";
    cell.className = "muted";
    return;
  }
  const caps = state.snapshot?.capabilities ?? {};
  if (!item.upgrade_editable || !caps.edit_upgrades || !state.snapshot.upgrade_catalog_available) {
    cell.textContent = item.upgrades.length ? item.upgrades.join(", ") : "нет";
    cell.className = "muted mono";
    return;
  }

  const current = item.upgrades;
  const effective = state.upgrades.get(item.handle) ?? current;
  const definitions = upgradeDefinitionsFor(item);
  const known = new Map(definitions.map((upgrade) => [upgrade.key, upgrade]));
  const keys = [...current, ...definitions.map((upgrade) => upgrade.key)]
    .filter((key, index, values) => values.indexOf(key) === index);
  const details = document.createElement("details");
  details.className = "upgrade-editor";
  const summary = document.createElement("summary");
  summary.textContent = `${effective.length} выбрано · изменить`;
  details.append(summary);
  const list = document.createElement("div");
  list.className = "upgrade-list";
  for (const key of keys) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = key;
    checkbox.checked = effective.includes(key);
    const definition = known.get(key);
    const text = definition
      ? (definition.name === key ? key : `${definition.name} · ${key}`)
      : `Неизвестный ID · ${key}`;
    label.append(checkbox, document.createTextNode(text));
    list.append(label);
  }
  details.append(list);
  const action = document.createElement("button");
  action.className = "button";
  action.type = "button";
  action.textContent = "Застейджить";
  action.addEventListener("click", () => {
    const desired = [...list.querySelectorAll("input:checked")].map((input) => input.value);
    if (desired.length === current.length && desired.every((key, index) => key === current[index])) {
      state.upgrades.delete(item.handle);
    } else {
      state.upgrades.set(item.handle, desired);
    }
    invalidate();
    renderInventory();
    renderChanges();
    setStatus(`Улучшения ${item.type_key} подготовлены; исходный файл не изменён`);
  });
  details.append(action);
  cell.append(details);
}

function placementLabel(placementType, slotId) {
  if (placementType === "slot" && slotId !== null && slotId !== undefined) {
    return `Слот ${slotId}`;
  }
  return { belt: "Пояс", ruck: "Рюкзак" }[placementType] ?? "Неизвестно";
}

function renderPlacementEditor(item, cell) {
  const caps = state.snapshot?.capabilities ?? {};
  if (!item.placement_editable || !caps.edit_placement) {
    return;
  }
  const current = [
    item.placement_type,
    item.placement_type === "slot" ? item.placement_slot : null,
  ];
  const effective = state.placements.get(item.handle) ?? current;
  const wrap = document.createElement("div");
  wrap.className = "placement-editor";
  const select = document.createElement("select");
  select.title = "Экспериментально: client-data SInvItemPlace; backup обязателен";
  const options = [
    ["ruck", null],
    ["belt", null],
    ...Array.from({ length: 13 }, (_, index) => ["slot", index + 1]),
  ];
  for (const [placementType, slotId] of options) {
    const option = document.createElement("option");
    option.value = slotId === null ? placementType : `${placementType}:${slotId}`;
    option.textContent = placementLabel(placementType, slotId);
    option.selected = placementType === effective[0] && slotId === effective[1];
    select.append(option);
  }
  const button = document.createElement("button");
  button.className = "button";
  button.type = "button";
  button.textContent = state.placements.has(item.handle) ? "Позиция*" : "Позиция";
  button.addEventListener("click", () => {
    const [placementType, rawSlot] = select.value.split(":");
    const slotId = rawSlot === undefined ? null : Number(rawSlot);
    if (placementType === current[0] && slotId === current[1]) {
      state.placements.delete(item.handle);
    } else {
      state.placements.set(item.handle, [placementType, slotId]);
    }
    invalidate();
    renderInventory();
    renderChanges();
    setStatus(`Позиция ${item.type_key} подготовлена; исходный файл не изменён`);
  });
  wrap.append(select, button);
  cell.append(wrap);
}

function renderInventory() {
  const body = el("inventory").tBodies[0];
  body.replaceChildren(...visibleItems().map((item) => {
    const tr = document.createElement("tr");
    const staged = state.stacks.get(item.handle);
    const stagedDurability = state.durability.get(item.handle);
    tr.className = state.detach.has(item.handle)
      ? "staged"
      : staged !== undefined || stagedDurability !== undefined || state.upgrades.has(item.handle) || state.placements.has(item.handle)
        ? "staged"
        : item.editable ? "" : "readonly";
    const iconTd = document.createElement("td");
    iconTd.className = "item-icon-cell";
    iconTd.append(itemGlyph(item));
    tr.append(iconTd);
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
    const upgradesTd = document.createElement("td");
    renderUpgradeEditor(item, upgradesTd);
    tr.append(upgradesTd);
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
      remove.disabled = item.remove_editable !== true;
      if (remove.disabled) {
        remove.title = item.remove_reason || "Удаление этого объекта заблокировано";
      }
      remove.addEventListener("click", () => {
        if (state.detach.has(item.handle)) state.detach.delete(item.handle);
        else {
          state.detach.add(item.handle);
          state.stacks.delete(item.handle);
          state.durability.delete(item.handle);
          state.upgrades.delete(item.handle);
        }
        invalidate();
        renderInventory();
        renderChanges();
      });
      td.append(document.createTextNode(" "));
      td.append(remove);
    }
    renderPlacementEditor(item, td);
    tr.append(td);
    return tr;
  }));
}

const EQUIPMENT_LOCATION_LABELS = {
  equipped: "экипировано",
  inventory: "инвентарь",
  belt: "пояс",
  unknown: "неизвестно",
};

function equipmentFilterMatches(item, filter) {
  if (filter === "staged") return state.durability.has(item.handle);
  if (filter === "damaged") return item.damaged === true;
  if (filter === "equipped") return item.location === "equipped";
  if (filter === "inventory") return item.location === "inventory" || item.location === "belt";
  if (filter === "weapon" || filter === "armor" || filter === "helmet") return item.category === filter;
  return true;
}

function visibleEquipment() {
  const query = el("equipment-search").value.trim().toLowerCase();
  const filter = el("equipment-filter").value;
  return (state.snapshot?.equipment ?? []).filter((item) => {
    if (!equipmentFilterMatches(item, filter)) return false;
    if (!query) return true;
    return [item.name, item.category, item.location, item.type_key, item.handle_hex]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
}

function equipmentSupportText(item) {
  const support = item.durability ?? {};
  return support.reason
    ? `${support.maturity}: ${support.reason}`
    : String(support.maturity ?? "unsupported");
}

function equipmentPercent() {
  const value = Number(el("equipment-percent").value);
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    setStatus("Прочность должна быть числом 0…100", "error");
    return null;
  }
  return value / 100;
}

function stageEquipmentRepair(handles, percentage) {
  if (!state.snapshot) return;
  const target = Number(percentage);
  if (!Number.isFinite(target) || target < 0 || target > 1) {
    setStatus("Прочность должна быть числом 0…100", "error");
    return;
  }
  const byHandle = new Map((state.snapshot.equipment ?? []).map((item) => [item.handle, item]));
  let changed = 0;
  const skipped = [];
  for (const handle of [...new Set(handles)]) {
    const item = byHandle.get(handle);
    if (!item) {
      skipped.push(`${handle}: не найден`);
      continue;
    }
    if (item.condition === null || item.condition === undefined) {
      skipped.push(`${item.name}: прочность не прочитана`);
      continue;
    }
    if (!item.durability_editable) {
      skipped.push(`${item.name}: ${equipmentSupportText(item)}`);
      continue;
    }
    if (Math.abs(target - item.condition) <= 0.000001) state.durability.delete(handle);
    else state.durability.set(handle, target);
    changed += 1;
  }
  invalidate();
  renderEquipment();
  renderInventory();
  renderChanges();
  const details = skipped.length ? ` Пропущено: ${skipped.slice(0, 3).join("; ")}` : "";
  el("equipment-status").textContent = `Подготовлено строк: ${changed}.${details}`;
  setStatus(
    changed ? `Прочность подготовлена: ${changed} предмет(ов); исходный файл не изменён` : "Нет безопасных изменений прочности",
    changed ? "" : "error",
  );
}

function resetEquipmentRepair(handles) {
  for (const handle of [...new Set(handles)]) state.durability.delete(handle);
  invalidate();
  renderEquipment();
  renderInventory();
  renderChanges();
  el("equipment-status").textContent = "Staged-изменения прочности выбранных предметов отменены.";
}

function renderEquipment() {
  const table = el("equipment");
  if (!table) return;
  const body = table.tBodies[0];
  body.replaceChildren(...visibleEquipment().map((item) => {
    const tr = document.createElement("tr");
    const staged = state.durability.get(item.handle);
    tr.className = staged === undefined
      ? (item.durability_editable ? "" : "readonly")
      : "staged";

    const icon = document.createElement("td");
    icon.className = "item-icon-cell";
    icon.append(itemGlyph(item));
    tr.append(icon);

    for (const value of [
      item.name,
      item.category,
      EQUIPMENT_LOCATION_LABELS[item.location] ?? item.location,
    ]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }

    const condition = document.createElement("td");
    if (item.condition === null || item.condition === undefined) {
      condition.textContent = "неизвестно";
      condition.className = "muted";
    } else if (item.durability_editable) {
      const input = document.createElement("input");
      input.className = "condition-input";
      input.type = "number";
      input.min = "0";
      input.max = "100";
      input.step = "0.1";
      input.value = ((staged ?? item.condition) * 100).toFixed(1);
      input.title = "Изменение подготовлено до предпросмотра; исходный файл не изменяется";
      input.addEventListener("change", () => {
        const value = Number(input.value);
        if (!Number.isFinite(value) || value < 0 || value > 100) {
          input.value = ((staged ?? item.condition) * 100).toFixed(1);
          return;
        }
        stageEquipmentRepair([item.handle], value / 100);
      });
      condition.append(input);
    } else {
      condition.textContent = `${(staged ?? item.condition) * 100}%`;
      condition.className = "muted";
    }
    tr.append(condition);

    const support = document.createElement("td");
    support.textContent = item.durability?.maturity ?? "unsupported";
    support.title = equipmentSupportText(item);
    support.className = item.durability_editable ? "" : "muted";
    tr.append(support);

    const upgrades = document.createElement("td");
    upgrades.textContent = item.upgrades === null
      ? "неизвестно"
      : item.upgrades.length ? item.upgrades.join(", ") : "нет";
    upgrades.className = item.upgrades_editable ? "" : "muted";
    tr.append(upgrades);

    for (const value of [item.type_key, item.handle_hex]) {
      const td = document.createElement("td");
      td.textContent = value;
      td.className = "mono";
      tr.append(td);
    }

    const action = document.createElement("td");
    const select = document.createElement("button");
    select.className = "button";
    select.type = "button";
    select.textContent = state.equipmentSelectedHandle === item.handle ? "Выбрано" : "Выбрать";
    select.disabled = !item.durability_editable;
    select.title = item.durability_editable ? "Выбрать для отдельной или массовой правки" : equipmentSupportText(item);
    select.addEventListener("click", () => {
      state.equipmentSelectedHandle = item.handle;
      renderEquipment();
    });
    action.append(select);
    tr.append(action);
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
    const label = item
      ? `${item.name} · ${item.handle_hex}`
      : `0x${handle.toString(16).padStart(8, "0")}`;
    const before = item?.condition === null || item?.condition === undefined
      ? "?"
      : `${(item.condition * 100).toFixed(1)}%`;
    items.push(`Прочность ${label}: ${before} → ${(condition * 100).toFixed(1)}% (experimental)`);
  }
  for (const [handle, values] of state.upgrades) {
    const item = state.snapshot.inventory.find((i) => i.handle === handle);
    items.push(`ОПАСНО: улучшения ${item?.handle_hex ?? `0x${handle.toString(16).padStart(8, "0")}`}: ${(item?.upgrades ?? []).join(", ") || "нет"} → ${values.join(", ") || "нет"}; backup обязателен`);
  }
  for (const [handle, [placementType, slotId]] of state.placements) {
    const item = state.snapshot.inventory.find((i) => i.handle === handle);
    const before = item?.position ?? "неизвестно";
    items.push(`ОПАСНО: позиция ${item?.handle_hex ?? `0x${handle.toString(16).padStart(8, "0")}`}: ${before} → ${placementLabel(placementType, slotId)}; backup обязателен`);
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
  el("download").disabled = !has && state.prepared === null;
  el("download").textContent = state.prepared === null
    ? "Проверить и скачать копию"
    : "Скачать копию";
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
    const upgrades = JSON.stringify([...state.upgrades.entries()]);
    const placements = JSON.stringify([...state.placements.entries()].map(([handle, [placementType, slotId]]) => [handle, placementType, slotId]));
    const result = JSON.parse(state.bridge.prepare(state.money, stacks, adds, detach, durability, relations, playerFaction, upgrades, placements));
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
    for (const [handle, before, after] of result.upgrades ?? []) {
      lines.push(`улучшения ${handle}: ${(before ?? []).join(", ") || "нет"} → ${(after ?? []).join(", ") || "нет"} (experimental)`);
    }
    for (const [handle, before, after] of result.placements ?? []) {
      const beforeLabel = placementLabel(before?.[0], before?.[1]);
      const afterLabel = placementLabel(after?.[0], after?.[1]);
      lines.push(`позиция ${handle}: ${beforeLabel} → ${afterLabel} (experimental)`);
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
    el("download").textContent = "Скачать копию";
    setStatus("Предпросмотр выполнен; исходный файл не изменялся");
  } catch (error) {
    fail(error);
  }
}

function download() {
  try {
    // The browser has no destination-side backup journal, so keep the same
    // immutable preview gate while reducing the common flow to one click.
    if (state.prepared === null) {
      preview();
      if (state.prepared === null) return;
    }
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
el("equipment-search").addEventListener("input", renderEquipment);
el("equipment-filter").addEventListener("change", renderEquipment);
el("equipment-repair-selected").addEventListener("click", () => {
  const target = equipmentPercent();
  if (target === null) return;
  if (state.equipmentSelectedHandle === null) {
    setStatus("Сначала выбери оборудование", "error");
    return;
  }
  stageEquipmentRepair([state.equipmentSelectedHandle], target);
});
el("equipment-repair-full").addEventListener("click", () => {
  if (state.equipmentSelectedHandle === null) {
    setStatus("Сначала выбери оборудование", "error");
    return;
  }
  el("equipment-percent").value = "100";
  stageEquipmentRepair([state.equipmentSelectedHandle], 1);
});
el("equipment-reset-selected").addEventListener("click", () => {
  if (state.equipmentSelectedHandle === null) {
    setStatus("Сначала выбери оборудование", "error");
    return;
  }
  resetEquipmentRepair([state.equipmentSelectedHandle]);
});
const stageEquipmentBulk = (filter) => {
  const target = equipmentPercent();
  if (target === null) return;
  const handles = (state.snapshot?.equipment ?? [])
    .filter((item) => equipmentFilterMatches(item, filter))
    .map((item) => item.handle);
  stageEquipmentRepair(handles, target);
};
el("equipment-repair-damaged").addEventListener("click", () => stageEquipmentBulk("damaged"));
el("equipment-repair-equipped").addEventListener("click", () => stageEquipmentBulk("equipped"));
el("equipment-repair-weapon").addEventListener("click", () => stageEquipmentBulk("weapon"));
el("equipment-repair-armor").addEventListener("click", () => stageEquipmentBulk("armor"));
el("equipment-repair-helmet").addEventListener("click", () => stageEquipmentBulk("helmet"));
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

const supportModal = el("support-modal");
el("support-button").addEventListener("click", () => {
  if (typeof supportModal.showModal === "function") {
    supportModal.showModal();
  } else {
    supportModal.hidden = false;
  }
});
el("support-close").addEventListener("click", () => {
  if (typeof supportModal.close === "function") {
    supportModal.close();
  } else {
    supportModal.hidden = true;
  }
});
supportModal.addEventListener("click", (event) => {
  if (event.target !== supportModal) return;
  if (typeof supportModal.close === "function") {
    supportModal.close();
  } else {
    supportModal.hidden = true;
  }
});
for (const button of document.querySelectorAll(".support-copy")) {
  button.addEventListener("click", async () => {
    const value = button.dataset.copy ?? "";
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const input = Object.assign(document.createElement("textarea"), { value });
        input.setAttribute("readonly", "");
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.append(input);
        input.select();
        const copied = document.execCommand("copy");
        input.remove();
        if (!copied) throw new Error("clipboard unavailable");
      }
      const original = button.textContent;
      button.textContent = "Copied";
      window.setTimeout(() => { button.textContent = original ?? "Copy"; }, 1200);
    } catch (error) {
      fail(`Не удалось скопировать: ${error}`);
    }
  });
}

el("preview").addEventListener("click", preview);
el("download").addEventListener("click", download);

el("file-input").disabled = true;
boot().catch(fail);
