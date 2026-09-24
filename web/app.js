// Browser build: the page is a thin shell around the project's shared core.
// The file stays in this tab; Steam Cloud, native folders and in-place backup
// operations deliberately remain desktop-only.

import { installCatalogs, loadCoreResources } from "./bootstrap.js";
import {
  BROWSER_UI_COPY,
  capabilityLabel,
  errorPresentation,
  integrityLabel,
  technicalDetails,
} from "./ux_copy.js";

const PYODIDE_VERSION = "0.28.3";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const OOZ_URL = "https://cdn.jsdelivr.net/npm/ooz-wasm@2.0.0/index.js";

const el = (id) => document.getElementById(id);
const status = el("status");
const errorAction = el("reference-error-action");
const detailsAction = el("reference-technical-details");
const detailsDialog = el("technical-details-dialog");
let technicalDetailText = "";

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
  referenceSelectedHandle: null,
  prepared: null,
  catalogsReady: null,
};

let referenceScreen = "library";

function refreshReferenceData() {
  if (state.snapshot) {
    renderReferenceSnapshot(state.snapshot);
    setStatus("Данные обновлены; исходный файл не изменён");
  } else {
    setStatus("Открой локальный файл сохранения", "error");
  }
}

function footerActionsFor(screen) {
  const actions = {
    library: [
      ["Enter", "Открыть", () => state.snapshot ? showReferenceScreen("editor") : el("file-input").click()],
      ["I", "Импорт", () => el("file-input").click()],
      ["R", "Обновить", refreshReferenceData],
      ["F", "Фильтр", () => el("reference-library-search")?.focus()],
    ],
    editor: [
      ["S", "Сохранить", () => { if (referenceChangeCount() > 0) showReferenceScreen("review"); }],
      ["F", "Фильтр", () => el("reference-inventory-search")?.focus()],
      ["Esc", "Назад", () => showReferenceScreen("library")],
    ],
    review: [
      ["Enter", "Подтвердить", () => el("reference-review-save")?.click()],
      ["Esc", "Отмена", () => showReferenceScreen("editor")],
    ],
    cloud: [["Esc", "Назад", () => showReferenceScreen("library")]],
    history: [["Esc", "Назад", () => showReferenceScreen("library")]],
    settings: [["Esc", "Назад", () => showReferenceScreen("library")]],
  };
  return actions[screen] ?? [];
}

function renderFooterActions() {
  const container = el("reference-footer-actions");
  if (!container) return;
  container.replaceChildren(...footerActionsFor(referenceScreen).map(([key, label, callback]) => {
    const button = document.createElement("button");
    button.className = "reference-footer-action";
    button.type = "button";
    button.dataset.shortcut = key;
    button.textContent = `${key}  ${label}`;
    button.addEventListener("click", callback);
    return button;
  }));
}

function setStatus(text, kind = "") {
  if (!status) return;
  status.textContent = text;
  status.className = `reference-footer-status${kind ? ` ${kind}` : ""}`;
  status.title = "";
  errorAction.hidden = true;
  errorAction.onclick = null;
  detailsAction.hidden = true;
  technicalDetailText = "";
}

function fail(error, kind = "generic") {
  console.error(error);
  const details = String(error && error.message ? error.message : error);
  const presentation = errorPresentation(kind, details);
  setStatus(presentation.message, "error");
  setTechnicalDetails(technicalDetails(presentation.technicalDetails, presentation.errorCode));
  if (kind === "open") {
    errorAction.textContent = presentation.primaryAction;
    errorAction.onclick = () => el("file-input").click();
    errorAction.hidden = false;
  } else if (kind === "verify") {
    errorAction.textContent = presentation.primaryAction;
    errorAction.onclick = () => showReferenceScreen("editor");
    errorAction.hidden = false;
  } else {
    errorAction.textContent = presentation.primaryAction;
    errorAction.onclick = () => setStatus("");
    errorAction.hidden = false;
  }
}

function setTechnicalDetails(value) {
  technicalDetailText = String(value ?? "");
  detailsAction.hidden = !technicalDetailText;
}

function showTechnicalDetails() {
  if (!technicalDetailText) return;
  el("technical-details-text").textContent = technicalDetailText;
  el("technical-details-copy").textContent = "Копировать";
  detailsDialog.showModal();
}

function showReferenceScreen(name) {
  referenceScreen = name;
  for (const screen of document.querySelectorAll(".reference-screen")) {
    screen.hidden = screen.id !== `reference-screen-${name}`;
    screen.classList.toggle("is-active", !screen.hidden);
  }
  for (const button of document.querySelectorAll(".reference-nav-button")) {
    button.classList.toggle("is-active", button.dataset.referenceScreen === name);
  }
  renderFooterActions();
}

function referenceChangeCount() {
  return state.stacks.size + state.durability.size + state.upgrades.size +
    state.placements.size + state.relations.size + state.adds.size +
    state.detach.size + (state.money === null ? 0 : 1) +
    (state.playerFaction === null ? 0 : 1);
}

function referenceItemStaged(item) {
  return state.stacks.has(item.handle) || state.durability.has(item.handle) ||
    state.upgrades.has(item.handle) || state.placements.has(item.handle) ||
    state.detach.has(item.handle);
}

function snapshotItem(handle) {
  return state.snapshot?.inventory?.find((item) => item.handle === handle) ?? null;
}

function setItemTechnicalDetails(item) {
  const lines = [];
  if (state.snapshot?.sha256) lines.push(`SHA-256 сохранения: ${state.snapshot.sha256}`);
  if (item) {
    lines.push(`Идентификатор предмета: ${item.handle_hex ?? item.handle}`);
    lines.push(`Ключ типа: ${item.type_key ?? "не определён"}`);
    if (item.remove_reason) lines.push(`Причина недоступности удаления: ${item.remove_reason}`);
  }
  setTechnicalDetails(technicalDetails(lines.join("\n")));
}

function formatCondition(value) {
  return value === null || value === undefined ? "—" : `${(Number(value) * 100).toFixed(0)}%`;
}

function placementLabel(placementType, slotId) {
  if (placementType === "slot" && slotId !== null && slotId !== undefined) return `Слот ${slotId}`;
  return { belt: "Пояс", ruck: "Рюкзак" }[placementType] ?? "Неизвестно";
}

function itemCategoryGlyph(category) {
  const value = String(category ?? "").toLowerCase();
  const glyph = document.createElement("span");
  glyph.className = `zone-item-glyph zone-item-glyph-${value || "item"}`;
  glyph.setAttribute("role", "img");
  glyph.setAttribute("aria-label", `Категория предмета: ${category || "неизвестно"}`);
  glyph.textContent = "—";
  return glyph;
}

function itemGlyph(item) {
  const candidates = [item.type_key, item.name].filter(Boolean);
  if (!candidates.length) return itemCategoryGlyph(item.category);
  const img = document.createElement("img");
  img.className = "zone-item-icon";
  img.loading = "lazy";
  img.decoding = "async";
  let candidateIndex = 0;
  const setSource = () => {
    const candidate = candidates[candidateIndex];
    img.alt = `Иконка предмета: ${item.name ?? item.category ?? "предмет"}`;
    img.title = "";
    img.src = `icons/${encodeURIComponent(candidate)}.png`;
  };
  img.addEventListener("error", () => {
    candidateIndex += 1;
    if (candidateIndex < candidates.length) setSource();
    else img.replaceWith(itemCategoryGlyph(item.category));
  });
  setSource();
  return img;
}

function addDetailField(container, label, control) {
  const row = document.createElement("label");
  row.className = "reference-field-row";
  const caption = document.createElement("span");
  caption.textContent = label;
  row.append(caption, control);
  container.append(row);
  return control;
}

function renderReferenceReview() {
  const table = el("reference-review-table");
  if (!table || !state.snapshot) return;
  const rows = [];
  if (state.money !== null) rows.push(["Баланс", String(state.snapshot.money ?? "—"), String(state.money)]);
  for (const [handle, count] of state.stacks) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? "Предмет", String(item?.count ?? "—"), String(count)]);
  }
  for (const [handle, condition] of state.durability) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? "Предмет", formatCondition(item?.condition), formatCondition(condition)]);
  }
  for (const [handle, placement] of state.placements) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? "Предмет", placementLabel(item?.placement_type, item?.placement_slot), placementLabel(placement[0], placement[1])]);
  }
  for (const [handle, values] of state.upgrades) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? "Предмет", upgradeNames(item, item?.upgrades), upgradeNames(item, values)]);
  }
  for (const [key, quantity] of state.adds) {
    const catalogItem = (state.snapshot.catalog_items ?? []).find((item) => item.key === key);
    rows.push([catalogItem?.name ?? "Предмет из каталога", "нет", `добавить × ${quantity}`]);
  }
  for (const handle of state.detach) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? "Предмет", "в сохранении", "удалить"]);
  }
  for (const [key, goodwill] of state.relations) {
    const row = state.snapshot.faction_relations?.find((entry) => entry.key === key);
    rows.push([row?.name ?? "Группировка", String(row?.value ?? 0), String(goodwill)]);
  }
  if (state.playerFaction !== null) rows.push(["Группировка игрока", "текущая", factionName(state.playerFaction)]);
  table.tBodies[0].replaceChildren(...(rows.length ? rows.map((values) => {
    const tr = document.createElement("tr");
    for (const value of values) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    return tr;
  }) : [Object.assign(document.createElement("tr"), {
    innerHTML: '<td colspan="3" class="reference-empty">Изменений ещё нет.</td>',
  })]));
  const count = referenceChangeCount();
  el("reference-review-save").disabled = count === 0;
  el("reference-save").textContent = `СОХРАНИТЬ ${count} ИЗМЕНЕНИЙ`;
  el("reference-save").disabled = count === 0;
}

function upgradeDefinitionsFor(item) {
  return (state.snapshot?.catalog_upgrades ?? []).filter((upgrade) =>
    (upgrade.applicable_item_keys ?? []).includes(item.type_key) || upgrade.item_key === item.type_key,
  );
}

function upgradeNames(item, keys) {
  const definitions = upgradeDefinitionsFor(item);
  return (keys ?? []).map((key) => definitions.find((entry) => entry.key === key)?.name ?? "Неизвестная модификация").join(", ") || "нет";
}

function factionName(key) {
  const faction = (state.snapshot?.catalog_factions ?? []).find((entry) => entry.key === key);
  return faction && faction.name !== faction.key
    ? faction.name
    : `Группировка ${faction?.numeric_id ?? ""}`.trim();
}

function renderReferenceItemDetail(item) {
  const fields = el("reference-item-fields");
  fields.replaceChildren();
  setItemTechnicalDetails(item);
  const reset = el("reference-item-reset");
  if (!item) {
    el("reference-item-name").textContent = "Предмет не выбран";
    el("reference-item-type").textContent = "Выбери строку инвентаря";
    el("reference-item-image").replaceChildren(document.createTextNode("—"));
    el("reference-item-detail").textContent = "Это значение нельзя изменить.";
    el("reference-item-gate").textContent = "НЕТ ВЫБОРА";
    reset.disabled = true;
    return;
  }
  const caps = state.snapshot.capabilities ?? {};
  const selectedImage = el("reference-item-image");
  selectedImage.replaceChildren(itemGlyph(item));
  el("reference-item-name").textContent = item.name ?? "Неизвестный объект";
  el("reference-item-type").textContent = item.category_label ?? item.category ?? "Предмет";
  el("reference-item-detail").textContent = `Позиция: ${placementLabel(item.placement_type, item.placement_slot)}. Это значение нельзя изменить.`;
  el("reference-item-detail").title = "";
  const writable = Boolean(item.editable || item.condition_editable || item.placement_editable || item.upgrade_editable || item.remove_editable);
  el("reference-item-gate").textContent = writable ? "МОЖНО ИЗМЕНИТЬ" : "ТОЛЬКО ПРОСМОТР";
  el("reference-item-gate").className = `reference-chip ${writable ? "success" : "warning"}`;
  reset.disabled = !referenceItemStaged(item);

  if (item.editable && caps.edit_stacks) {
    const input = document.createElement("input");
    input.type = "number";
    input.min = "1";
    input.max = String(state.snapshot.stack_max ?? 1000000);
    input.value = String(state.stacks.get(item.handle) ?? item.count ?? 1);
    input.addEventListener("change", () => stageStack(item, input.value));
    addDetailField(fields, "Количество", input);
  }
  if (item.condition_editable && caps.edit_durability) {
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "100";
    input.step = "0.1";
    input.value = String(((state.durability.get(item.handle) ?? item.condition) * 100).toFixed(1));
    input.addEventListener("change", () => stageDurability(item, input.value));
    addDetailField(fields, "Состояние", input);
  }
  if (item.placement_editable && caps.edit_placement) {
    const select = document.createElement("select");
    const current = state.placements.get(item.handle) ?? [item.placement_type, item.placement_slot];
    for (const [placementType, slotId] of [["ruck", null], ["belt", null], ...Array.from({ length: 13 }, (_, index) => ["slot", index + 1])]) {
      const option = document.createElement("option");
      option.value = slotId === null ? placementType : `${placementType}:${slotId}`;
      option.textContent = placementLabel(placementType, slotId);
      option.selected = placementType === current[0] && slotId === current[1];
      select.append(option);
    }
    select.title = "Экспериментальная функция. Перед изменениями создаётся резервная копия.";
    select.addEventListener("change", () => {
      const [placementType, rawSlot] = select.value.split(":");
      const slotId = rawSlot === undefined ? null : Number(rawSlot);
      if (placementType === item.placement_type && slotId === item.placement_slot) state.placements.delete(item.handle);
      else state.placements.set(item.handle, [placementType, slotId]);
      invalidate();
      renderReferenceEditor(state.snapshot);
    });
    addDetailField(fields, "Размещение", select);
  }
  if (Array.isArray(item.upgrades)) {
    const definitions = upgradeDefinitionsFor(item);
    if (item.upgrade_editable && caps.edit_upgrades && state.snapshot.upgrade_catalog_available) {
      const select = document.createElement("select");
      select.multiple = true;
      select.size = Math.min(5, Math.max(2, definitions.length));
      const effective = state.upgrades.get(item.handle) ?? item.upgrades;
      for (const key of [...new Set([...item.upgrades, ...definitions.map((entry) => entry.key)])]) {
        const option = document.createElement("option");
        const definition = definitions.find((entry) => entry.key === key);
        option.value = key;
        option.textContent = definition ? definition.name : "Неизвестное улучшение";
        option.title = "";
        option.selected = effective.includes(key);
        select.append(option);
      }
      select.title = "Экспериментальная функция. Перед изменениями создаётся резервная копия.";
      select.addEventListener("change", () => {
        const values = [...select.selectedOptions].map((option) => option.value);
        if (values.length === item.upgrades.length && values.every((key, index) => key === item.upgrades[index])) state.upgrades.delete(item.handle);
        else state.upgrades.set(item.handle, values);
        invalidate();
        renderReferenceEditor(state.snapshot);
      });
      addDetailField(fields, "Улучшения", select);
    } else {
      const evidence = document.createElement("div");
      evidence.className = "reference-readonly-detail";
      evidence.textContent = "Улучшения доступны только для просмотра.";
      evidence.removeAttribute("title");
      fields.append(evidence);
    }
  }
  if (item.remove_editable && caps.remove_items) {
    const remove = document.createElement("button");
    remove.className = "reference-danger";
    remove.type = "button";
    remove.textContent = state.detach.has(item.handle) ? "ОТМЕНИТЬ УДАЛЕНИЕ" : "УДАЛИТЬ ПРЕДМЕТ";
    remove.disabled = !item.remove_editable;
    remove.title = "Удалить предмет";
    remove.addEventListener("click", () => {
      if (state.detach.has(item.handle)) state.detach.delete(item.handle);
      else {
        state.detach.add(item.handle);
        state.stacks.delete(item.handle);
        state.durability.delete(item.handle);
        state.upgrades.delete(item.handle);
      }
      invalidate();
      renderReferenceEditor(state.snapshot);
    });
    fields.append(remove);
  }
}

function visibleReferenceItems(s) {
  const query = el("reference-inventory-search").value.trim().toLowerCase();
  const filter = el("reference-inventory-filter").value;
  return (s.inventory ?? []).filter((item) => {
    // Tabs use the shared product taxonomy; the parser's own labels
    // ("Патроны", "Гранаты/стак") are never compared with the tab keys.
    const category = String(item.product_category ?? "other");
    const groups = { outfit: ["armor", "helmet", "device"], other: ["other", "module"] };
    const categoryMatch = filter === "all" || (groups[filter] ?? [filter]).includes(category);
    if (!categoryMatch) return false;
    return !query || [item.name, item.category, item.category_label, item.type_key, item.handle_hex].join(" ").toLowerCase().includes(query);
  });
}

function stageStack(item, rawValue) {
  const value = Number(rawValue);
  const max = Number(state.snapshot?.stack_max ?? 1000000);
  if (!Number.isInteger(value) || value < 1 || value > max) {
    setStatus(`Количество должно быть целым числом 1…${max}`, "error");
    return;
  }
  if (value === item.count) state.stacks.delete(item.handle);
  else state.stacks.set(item.handle, value);
  invalidate();
  renderReferenceEditor(state.snapshot);
}

function stageDurability(item, rawValue) {
  const value = Number(rawValue);
  if (!Number.isFinite(value) || value < 0 || value > 100) {
    setStatus("Состояние должно быть числом 0…100", "error");
    return;
  }
  const normalized = value / 100;
  if (Math.abs(normalized - item.condition) <= 0.000001) state.durability.delete(item.handle);
  else state.durability.set(item.handle, normalized);
  invalidate();
  renderReferenceEditor(state.snapshot);
}

function renderReferenceEditor(s) {
  const table = el("reference-inventory-table");
  if (!table) return;
  const items = visibleReferenceItems(s);
  table.tBodies[0].replaceChildren(...(items.length ? items.map((item) => {
    const row = document.createElement("tr");
    if (item.handle === state.referenceSelectedHandle) row.classList.add("selected");
    if (referenceItemStaged(item)) row.classList.add("staged");
    const selectCell = document.createElement("td");
    const select = document.createElement("button");
    select.className = "reference-row-select";
    select.type = "button";
    select.textContent = item.handle === state.referenceSelectedHandle ? "✓" : "□";
    select.title = "Выбрать предмет";
    select.addEventListener("click", () => {
      state.referenceSelectedHandle = item.handle;
      renderReferenceEditor(s);
    });
    selectCell.append(itemGlyph(item), select);
    row.append(selectCell);
    row.addEventListener("click", (event) => {
      if (event.target.closest("button, input, select")) return;
      state.referenceSelectedHandle = item.handle;
      renderReferenceEditor(s);
    });
    for (const value of [item.name, item.category_label ?? item.category]) {
      const cell = document.createElement("td");
      cell.textContent = value ?? "—";
      row.append(cell);
    }
    const count = document.createElement("td");
    count.textContent = item.count === null || item.count === undefined ? "—" : String(state.stacks.get(item.handle) ?? item.count);
    row.append(count);
    const weight = document.createElement("td");
    weight.textContent = item.total_weight === null || item.total_weight === undefined ? "—" : Number(item.total_weight).toFixed(1);
    row.append(weight);
    const condition = document.createElement("td");
    condition.textContent = formatCondition(state.durability.get(item.handle) ?? item.condition);
    row.append(condition);
    const support = document.createElement("td");
    support.textContent = item.condition_editable || item.editable || item.placement_editable || item.upgrade_editable ? "МОЖНО ИЗМЕНИТЬ" : "ТОЛЬКО ПРОСМОТР";
    support.className = support.textContent === "ТОЛЬКО ПРОСМОТР" ? "muted" : "";
    row.append(support);
    const action = document.createElement("td");
    action.textContent = item.remove_editable ? "…" : "—";
    row.append(action);
    return row;
  }) : [Object.assign(document.createElement("tr"), {
    innerHTML: '<td colspan="8" class="reference-empty">Предметов не найдено.</td>',
  })]));
  el("reference-item-count").textContent = `Элементов: ${s.inventory_count ?? items.length}`;
  const selected = (s.inventory ?? []).find((item) => item.handle === state.referenceSelectedHandle) ?? items[0] ?? null;
  if (selected && state.referenceSelectedHandle === null) state.referenceSelectedHandle = selected.handle;
  renderReferenceItemDetail(selected);
  renderReferenceReview();
  renderReferenceAdd(s);
}

function renderReferenceAdd(s) {
  const select = el("reference-add-select");
  const button = el("reference-add-button");
  if (!select || !button) return;
  // Named entries first; an unnamed definition shows its key instead of
  // hundreds of identical "Предмет из каталога" options.
  const catalogItems = [...(s.catalog_items ?? [])].sort((a, b) =>
    Number(a.name === a.key) - Number(b.name === b.key) || String(a.name).localeCompare(String(b.name), "ru"));
  select.replaceChildren(...catalogItems.map((item) => {
    const option = document.createElement("option");
    option.value = item.key;
    option.textContent = item.name;
    option.title = item.key;
    return option;
  }));
  const enabled = Boolean(s.capabilities?.add_items && s.catalog_available && select.options.length);
  select.disabled = !enabled;
  button.disabled = !enabled;
}

function renderReferenceCharacter(s) {
  const panel = el("reference-character-details");
  const factions = (s.catalog_factions ?? []).filter((faction) => faction.numeric_id !== null && faction.numeric_id !== undefined);
  const rows = s.faction_relations ?? [];
  const supported = Boolean(s.faction_catalog_available && (rows.length || factions.length));
  panel.replaceChildren();
  panel.hidden = !supported;
  if (!supported) {
    panel.textContent = "Данные о персонаже и группировках недоступны для этого сохранения.";
    panel.hidden = false;
    return;
  }
  if (s.player_faction_editable && factions.length) {
    const select = document.createElement("select");
    for (const faction of factions) {
      const option = document.createElement("option");
      option.value = faction.key;
      option.textContent = faction.name === faction.key ? `Группировка ${faction.numeric_id}` : faction.name;
      option.title = "";
      option.selected = faction.numeric_id === s.player_faction_index || faction.key === state.playerFaction;
      select.append(option);
    }
    const button = document.createElement("button");
    button.className = "reference-secondary";
    button.type = "button";
    button.textContent = state.playerFaction === null ? "ИЗМЕНИТЬ ГРУППИРОВКУ" : "ГРУППИРОВКА*";
    button.addEventListener("click", () => {
      const current = factions.find((entry) => entry.numeric_id === s.player_faction_index)?.key;
      state.playerFaction = select.value === current ? null : select.value;
      invalidate();
      renderReferenceCharacter(s);
      renderReferenceReview();
    });
    addDetailField(panel, "Игрок", select);
    panel.append(button);
  }
  for (const relation of rows.slice(0, 8)) {
    const input = document.createElement("input");
    const current = relation.stored ? Number(relation.value) : 0;
    input.type = "number";
    input.value = String(state.relations.get(relation.key) ?? current);
    input.disabled = !s.capabilities?.edit_relations;
    input.addEventListener("change", () => {
      const value = Number(input.value);
      const min = Number(s.faction_goodwill_min ?? -2147483648);
      const max = Number(s.faction_goodwill_max ?? 2147483647);
      if (!Number.isInteger(value) || value < min || value > max) return;
      if (value === current) state.relations.delete(relation.key);
      else state.relations.set(relation.key, value);
      invalidate();
      renderReferenceCharacter(s);
      renderReferenceReview();
    });
    addDetailField(panel, relation.name ?? "Группировка", input);
  }
}

function renderReferenceSnapshot(s) {
  el("reference-game-count").textContent = "1 сохранение";
  el("reference-preview-name").textContent = s.name;
  const previewMeta = el("reference-preview-meta");
  previewMeta.replaceChildren();
  for (const [index, line] of [
    `Игра: ${s.format_title}`,
    "Источник: локальное сохранение",
    `Размер: ${s.size_text}`,
    `${BROWSER_UI_COPY.integrity}: ${integrityLabel(s)}`,
  ].entries()) {
    if (index) previewMeta.append(document.createElement("br"));
    previewMeta.append(document.createTextNode(line));
  }
  previewMeta.title = "";
  el("reference-preview-status").textContent = integrityLabel(s).toUpperCase();
  el("reference-activity").textContent = `Проанализирован ${s.name}; исходный файл не изменён.`;
  const caps = s.capabilities ?? {};
  const editable = Boolean(caps.edit_money || caps.edit_stacks || caps.edit_durability || caps.edit_placement || caps.edit_upgrades);
  el("reference-preview-capability").textContent = capabilityLabel(editable);
  el("reference-preview-capability").className = `reference-chip ${editable ? "success" : "warning"}`;
  el("reference-summary-money").innerHTML = `ДЕНЬГИ<br>${s.money ?? "—"} ₽`;
  el("reference-summary-items").innerHTML = `ПРЕДМЕТЫ<br>${s.inventory_count ?? "—"}`;
  el("reference-summary-equipment").innerHTML = `ЭКИПИРОВКА<br>${s.equipment_count ?? "—"}`;
  el("reference-summary-condition").innerHTML = `${BROWSER_UI_COPY.integritySummary}<br>${integrityLabel(s)}`;
  el("reference-editor-breadcrumb").textContent = `${s.format_title}  ›  ${s.name}`;
  el("reference-editor-state").textContent = capabilityLabel(editable);
  el("reference-editor-state").className = `reference-chip ${editable ? "success" : "warning"}`;
  el("reference-money").textContent = `ДЕНЬГИ  ${s.money === null ? "—" : s.money} ₽`;
  el("reference-money-input").value = String(s.money ?? 0);
  el("reference-money-input").disabled = !s.money_editable;
  el("reference-money-clear").disabled = state.money === null;
  el("reference-weight").textContent = "ВЕС  — кг";
  el("reference-source").innerHTML = "Источник<br>Локальный файл";
  el("reference-integrity").innerHTML = `${BROWSER_UI_COPY.integrity}<br>${integrityLabel(s)}`;
  el("reference-editor-capability").innerHTML = `Статус<br>${editable ? "Редактируемый" : "Только просмотр"}`;
  el("reference-equipment-summary").textContent = `${s.equipment_count ?? 0} объектов оборудования · неподтверждённые данные нельзя изменить`;
  renderReferenceEditor(s);
  renderReferenceCharacter(s);
}

function renderSnapshot(s) {
  renderReferenceSnapshot(s);
  showReferenceScreen("editor");
}

async function boot() {
  setStatus(BROWSER_UI_COPY.startupLoading, "busy");
  const { bridgeSource, bundle, ooz, py } = await loadCoreResources({
    oozUrl: OOZ_URL,
    pyodideUrl: PYODIDE_URL,
  });
  setStatus(BROWSER_UI_COPY.startupPreparing, "busy");
  py.FS.mkdirTree("/core/editor");
  for (const [name, source] of Object.entries(bundle.files)) py.FS.writeFile(`/core/${name}`, source, { encoding: "utf8" });
  py.FS.writeFile("/core/web_bridge.py", bridgeSource, { encoding: "utf8" });
  py.runPython(`import sys; sys.path.insert(0, "/core")`);
  globalThis.__oozDecompress = (stream, size) => ooz.decompress(stream, size);
  const bridge = py.pyimport("web_bridge");
  bridge.install_decoder(globalThis.__oozDecompress);
  state.py = py;
  state.bridge = bridge;
  state.catalogsReady = installCatalogs({ bridge });
  state.catalogsReady.catch(fail);
  el("file-input").disabled = false;
  setStatus("Редактор готов. Выбери локальное сохранение.");
  state.catalogsReady.then(
    () => { if (!state.snapshot) setStatus("Приложение готово. Открой локальный файл сохранения."); },
    () => {},
  );
}

async function openFile(file) {
  if (!state.bridge || !state.catalogsReady) return;
  setStatus("Открытие сохранения…", "busy");
  try {
    const bytesReady = file.arrayBuffer();
    await state.catalogsReady;
    const bytes = new Uint8Array(await bytesReady);
    const snapshot = JSON.parse(state.bridge.analyze(bytes, file.name));
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
    state.referenceSelectedHandle = null;
    state.prepared = null;
    renderSnapshot(snapshot);
    setStatus("Сохранение проверено; исходный файл не изменён");
    setItemTechnicalDetails(snapshotItem(state.referenceSelectedHandle));
  } catch (error) {
    fail(error, "open");
  }
}

function invalidate() {
  if (state.prepared !== null) state.prepared = null;
  if (state.snapshot) {
    renderReferenceReview();
    el("reference-review-status").textContent = "Изменения готовы к проверке; исходный файл не изменён.";
  }
}

function preview() {
  try {
    if (!state.snapshot || !state.bridge) throw new Error("Сначала открой сохранение");
    setStatus("Проверка изменений и создание копии…", "busy");
    const result = JSON.parse(state.bridge.prepare(
      state.money,
      JSON.stringify([...state.stacks.entries()]),
      JSON.stringify([...state.adds.entries()]),
      JSON.stringify([...state.detach].map((handle) => [handle, true])),
      JSON.stringify([...state.durability.entries()]),
      JSON.stringify([...state.relations.entries()]),
      JSON.stringify(state.playerFaction),
      JSON.stringify([...state.upgrades.entries()]),
      JSON.stringify([...state.placements.entries()].map(([handle, [placementType, slotId]]) => [handle, placementType, slotId])),
    ));
    state.prepared = result;
    el("reference-review-status").textContent = `Копия проверена (${result.size_text}). Оригинальный файл пока не изменён.`;
    setStatus("Проверка выполнена; можно скачать копию");
    setTechnicalDetails(technicalDetails(`SHA-256 копии: ${result.output_sha256}`));
    return result;
  } catch (error) {
    fail(error, "verify");
    return null;
  }
}

function download() {
  try {
    if (state.prepared === null && preview() === null) return;
    const bytes = state.bridge.output_bytes().toJs();
    const match = state.snapshot.name.match(/\.(sav|scop|scs)$/i);
    const extension = match ? `.${match[1].toLowerCase()}` : ".sav";
    const name = state.snapshot.name.replace(/\.(sav|scop|scs)$/i, "") + "_edited" + extension;
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
    const link = Object.assign(document.createElement("a"), { href: url, download: name });
    link.click();
    URL.revokeObjectURL(url);
    setStatus(`Сохранена проверенная копия ${name}; исходный файл не изменён.`);
    setTechnicalDetails(technicalDetails(`SHA-256 копии: ${state.prepared.output_sha256}`));
  } catch (error) {
    fail(error, "verify");
  }
}

for (const button of document.querySelectorAll(".reference-nav-button")) {
  button.addEventListener("click", () => showReferenceScreen(button.dataset.referenceScreen));
}
el("reference-open").addEventListener("click", () => el("file-input").click());
el("reference-refresh").addEventListener("click", refreshReferenceData);
el("reference-history").addEventListener("click", () => showReferenceScreen("history"));
el("reference-editor-back").addEventListener("click", () => showReferenceScreen("library"));
el("reference-character").addEventListener("click", () => {
  const details = el("reference-character-details");
  if (!state.snapshot) return;
  renderReferenceCharacter(state.snapshot);
  details.hidden = !details.hidden;
  setStatus(details.hidden ? "Персонаж скрыт" : "Данные о персонаже и группировках показаны.");
});
el("reference-save").addEventListener("click", () => {
  if (referenceChangeCount() > 0) showReferenceScreen("review");
});
el("reference-review-save").addEventListener("click", () => download());
detailsAction.addEventListener("click", showTechnicalDetails);
el("technical-details-close").addEventListener("click", () => detailsDialog.close());
el("technical-details-copy").addEventListener("click", async () => {
  const text = el("technical-details-text").textContent ?? "";
  try {
    await navigator.clipboard.writeText(text);
    el("technical-details-copy").textContent = "Скопировано";
  } catch {
    const fallback = document.createElement("textarea");
    fallback.value = text;
    fallback.setAttribute("readonly", "");
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.append(fallback);
    fallback.select();
    if (document.execCommand("copy")) {
      el("technical-details-copy").textContent = "Скопировано";
    }
    fallback.remove();
  }
});
el("reference-library-search").addEventListener("input", () => {
  const query = el("reference-library-search").value.trim().toLowerCase();
  const row = el("reference-save-table").tBodies[0].firstElementChild;
  if (row && state.snapshot) row.hidden = Boolean(query && !state.snapshot.name.toLowerCase().includes(query));
});
el("reference-inventory-search").addEventListener("input", () => {
  if (state.snapshot) renderReferenceEditor(state.snapshot);
});
el("reference-inventory-filter").addEventListener("change", () => {
  if (state.snapshot) renderReferenceEditor(state.snapshot);
});
el("reference-money-input").addEventListener("input", () => {
  if (!state.snapshot?.money_editable) return;
  const value = Number(el("reference-money-input").value);
  if (!Number.isInteger(value) || value < 0 || value > 2_000_000_000) {
    setStatus("Сумма должна быть целым числом 0…2 000 000 000", "error");
    return;
  }
  state.money = value === state.snapshot.money ? null : value;
  invalidate();
  el("reference-money").textContent = `ДЕНЬГИ  ${value} ₽`;
  el("reference-money-clear").disabled = state.money === null;
  setStatus("Баланс изменён в памяти; исходный файл не изменён");
});
el("reference-money-clear").addEventListener("click", () => {
  state.money = null;
  if (state.snapshot) {
    invalidate();
    renderReferenceSnapshot(state.snapshot);
  }
});
el("reference-item-reset").addEventListener("click", () => {
  const handle = state.referenceSelectedHandle;
  if (handle === null) return;
  state.stacks.delete(handle);
  state.durability.delete(handle);
  state.upgrades.delete(handle);
  state.placements.delete(handle);
  state.detach.delete(handle);
  invalidate();
  renderReferenceEditor(state.snapshot);
});
el("reference-add-button").addEventListener("click", () => {
  const key = el("reference-add-select").value;
  const quantity = Number(el("reference-add-quantity").value);
  const definition = (state.snapshot?.catalog_items ?? []).find((item) => item.key === key);
  const max = Number(definition?.max_stack ?? 65535);
  if (!key || !Number.isInteger(quantity) || quantity < 1 || quantity > max) {
    setStatus(`Количество должно быть целым числом 1…${max}`, "error");
    return;
  }
  state.adds.set(key, quantity);
  invalidate();
  renderReferenceEditor(state.snapshot);
  setStatus(`Добавлен предмет: ${definition?.name ?? "из каталога"}. Оригинальный файл пока не изменён.`);
});
el("file-input").addEventListener("change", (event) => {
  const file = event.target.files?.[0];
  if (file) openFile(file);
});

const supportModal = el("support-modal");
el("support-button").addEventListener("click", () => {
  if (typeof supportModal.showModal === "function") supportModal.showModal();
  else supportModal.hidden = false;
});
el("support-close").addEventListener("click", () => {
  if (typeof supportModal.close === "function") supportModal.close();
  else supportModal.hidden = true;
});
for (const button of document.querySelectorAll(".support-copy")) {
  button.addEventListener("click", async () => {
    const value = button.dataset.copy ?? "";
    let copied = false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        copied = true;
      }
    } catch (_error) {
      copied = false;
    }
    if (!copied) {
      const input = document.createElement("textarea");
      input.value = value;
      document.body.append(input);
      input.select();
      copied = document.execCommand("copy");
      input.remove();
    }
    if (copied) button.textContent = "Скопировано";
    else button.textContent = "Не удалось скопировать";
    setTimeout(() => { button.textContent = "Копировать"; }, 1400);
  });
}

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const activeTag = document.activeElement?.tagName;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(activeTag) && event.key !== "Escape") return;
  const pressedKey = event.key === "Escape" ? "esc" : event.key.toLowerCase();
  const action = footerActionsFor(referenceScreen).find(([key]) => key.toLowerCase() === pressedKey);
  if (!action) return;
  event.preventDefault();
  action[2]();
});

const settingsCategoryIcons = ["settings", "paths", "backups", "cloud", "diagnostics", "interface", "support"];
for (const [index, button] of [...document.querySelectorAll(".reference-settings-category")].entries()) {
  const icon = button.querySelector("img");
  if (icon && settingsCategoryIcons[index]) {
    icon.src = `assets/ui/shell_icons/${settingsCategoryIcons[index]}.svg`;
  }
}

renderFooterActions();

boot().catch(fail);
