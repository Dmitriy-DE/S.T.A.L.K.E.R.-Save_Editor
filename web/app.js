// Browser build: the page is a thin shell around the project's shared core.
// The file stays in this tab; Steam Cloud, native folders and in-place backup
// operations deliberately remain desktop-only.

import { installCatalogs, loadCoreResources } from "./bootstrap.js";
import { fadeIn, play, setSoundTheme } from "./effects.js";
import { catalogSource, currentLanguage, t, tn } from "./i18n.js";
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
    setStatus(t("Данные обновлены; исходный файл не изменён"));
  } else {
    setStatus(t("Открой локальный файл сохранения"), "error");
  }
}

function footerActionsFor(screen) {
  const actions = {
    library: [
      ["Enter", t("Открыть"), () => state.snapshot ? showReferenceScreen("editor") : el("file-input").click()],
      ["I", t("Импорт"), () => el("file-input").click()],
      ["R", t("Обновить"), refreshReferenceData],
      ["F", t("Фильтр"), () => el("reference-library-search")?.focus()],
    ],
    editor: [
      ["S", t("Сохранить"), () => { if (referenceChangeCount() > 0) showReferenceScreen("review"); }],
      ["F", t("Фильтр"), () => el("reference-inventory-search")?.focus()],
      ["Esc", t("Назад"), () => showReferenceScreen("library")],
    ],
    review: [
      ["Enter", t("Подтвердить"), () => el("reference-review-save")?.click()],
      ["Esc", t("Отмена"), () => showReferenceScreen("editor")],
    ],
    cloud: [["Esc", t("Назад"), () => showReferenceScreen("library")]],
    history: [["Esc", t("Назад"), () => showReferenceScreen("library")]],
    settings: [["Esc", t("Назад"), () => showReferenceScreen("library")]],
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
  play("error");
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
  el("technical-details-copy").textContent = t("Копировать");
  detailsDialog.showModal();
}

function showReferenceScreen(name) {
  referenceScreen = name;
  for (const screen of document.querySelectorAll(".reference-screen")) {
    screen.hidden = screen.id !== `reference-screen-${name}`;
    screen.classList.toggle("is-active", !screen.hidden);
    if (!screen.hidden) fadeIn(screen);
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
  if (state.snapshot?.sha256) lines.push(t("SHA-256 сохранения: {0}", state.snapshot.sha256));
  if (item) {
    lines.push(t("Идентификатор предмета: {0}", item.handle_hex ?? item.handle));
    lines.push(t("Ключ типа: {0}", item.type_key ?? t("не определён")));
    if (item.remove_reason) lines.push(t("Причина недоступности удаления: {0}", item.remove_reason));
  }
  setTechnicalDetails(technicalDetails(lines.join("\n")));
}

function formatCondition(value) {
  return value === null || value === undefined ? "—" : `${(Number(value) * 100).toFixed(0)}%`;
}

function placementLabel(placementType, slotId) {
  if (placementType === "slot" && slotId !== null && slotId !== undefined) return t("Слот {0}", slotId);
  return { belt: t("Пояс"), ruck: t("Рюкзак") }[placementType] ?? t("Неизвестно");
}

function itemCategoryGlyph(category) {
  const value = String(category ?? "").toLowerCase();
  const glyph = document.createElement("span");
  glyph.className = `zone-item-glyph zone-item-glyph-${value || "item"}`;
  glyph.setAttribute("role", "img");
  glyph.setAttribute("aria-label", t("Категория предмета: {0}", category || t("неизвестно")));
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
    img.alt = t("Иконка предмета: {0}", item.name ?? item.category ?? t("предмет"));
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
  if (state.money !== null) rows.push([t("Баланс"), String(state.snapshot.money ?? "—"), String(state.money)]);
  for (const [handle, count] of state.stacks) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? t("Предмет"), String(item?.count ?? "—"), String(count)]);
  }
  for (const [handle, condition] of state.durability) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? t("Предмет"), formatCondition(item?.condition), formatCondition(condition)]);
  }
  for (const [handle, placement] of state.placements) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? t("Предмет"), placementLabel(item?.placement_type, item?.placement_slot), placementLabel(placement[0], placement[1])]);
  }
  for (const [handle, values] of state.upgrades) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? t("Предмет"), upgradeNames(item, item?.upgrades), upgradeNames(item, values)]);
  }
  for (const [key, quantity] of state.adds) {
    const catalogItem = (state.snapshot.catalog_items ?? []).find((item) => item.key === key);
    rows.push([catalogItem?.name ?? t("Предмет из каталога"), t("нет"), t("добавить × {0}", quantity)]);
  }
  for (const handle of state.detach) {
    const item = snapshotItem(handle);
    rows.push([item?.name ?? t("Предмет"), t("в сохранении"), t("удалить")]);
  }
  for (const [key, goodwill] of state.relations) {
    const row = state.snapshot.faction_relations?.find((entry) => entry.key === key);
    rows.push([row?.name ?? t("Группировка"), String(row?.value ?? 0), String(goodwill)]);
  }
  if (state.playerFaction !== null) rows.push([t("Группировка игрока"), t("текущая"), factionName(state.playerFaction)]);
  table.tBodies[0].replaceChildren(...(rows.length ? rows.map((values) => {
    const tr = document.createElement("tr");
    for (const value of values) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    return tr;
  }) : [Object.assign(document.createElement("tr"), {
    innerHTML: t("<td colspan=\"3\" class=\"reference-empty\">Изменений ещё нет.</td>"),
  })]));
  const count = referenceChangeCount();
  el("reference-review-save").disabled = count === 0;
  el("reference-save").textContent = t("СОХРАНИТЬ {0}", t("{0} {1}", count, tn(count, "ИЗМЕНЕНИЕ", "ИЗМЕНЕНИЯ", "ИЗМЕНЕНИЙ")));
  el("reference-save").disabled = count === 0;
}

function upgradeDefinitionsFor(item) {
  return (state.snapshot?.catalog_upgrades ?? []).filter((upgrade) =>
    (upgrade.applicable_item_keys ?? []).includes(item.type_key) || upgrade.item_key === item.type_key,
  );
}

function upgradeNames(item, keys) {
  const definitions = upgradeDefinitionsFor(item);
  return (keys ?? []).map((key) => definitions.find((entry) => entry.key === key)?.name ?? t("Неизвестная модификация")).join(", ") || t("нет");
}

function factionName(key) {
  const faction = (state.snapshot?.catalog_factions ?? []).find((entry) => entry.key === key);
  return faction && faction.name !== faction.key
    ? faction.name
    : t("Группировка {0}", faction?.numeric_id ?? "").trim();
}

function renderReferenceItemDetail(item) {
  const fields = el("reference-item-fields");
  fields.replaceChildren();
  setItemTechnicalDetails(item);
  const reset = el("reference-item-reset");
  if (!item) {
    el("reference-item-name").textContent = t("Предмет не выбран");
    el("reference-item-type").textContent = t("Выбери строку инвентаря");
    el("reference-item-image").replaceChildren(document.createTextNode("—"));
    el("reference-item-detail").textContent = t("Это значение нельзя изменить.");
    el("reference-item-gate").textContent = t("НЕТ ВЫБОРА");
    reset.disabled = true;
    return;
  }
  const caps = state.snapshot.capabilities ?? {};
  const selectedImage = el("reference-item-image");
  selectedImage.replaceChildren(itemGlyph(item));
  el("reference-item-name").textContent = item.name ?? t("Неизвестный объект");
  el("reference-item-type").textContent = item.category_label ?? item.category ?? t("Предмет");
  el("reference-item-detail").textContent = t("Позиция: {0}. Это значение нельзя изменить.", placementLabel(item.placement_type, item.placement_slot));
  el("reference-item-detail").title = "";
  const writable = Boolean(item.editable || item.condition_editable || item.placement_editable || item.upgrade_editable || item.remove_editable);
  el("reference-item-gate").textContent = writable ? t("МОЖНО ИЗМЕНИТЬ") : t("ТОЛЬКО ЧТЕНИЕ");
  el("reference-item-gate").className = `reference-chip ${writable ? "success" : "warning"}`;
  reset.disabled = !referenceItemStaged(item);

  if (item.editable && caps.edit_stacks) {
    const input = document.createElement("input");
    input.type = "number";
    input.min = "1";
    input.max = String(state.snapshot.stack_max ?? 1000000);
    input.value = String(state.stacks.get(item.handle) ?? item.count ?? 1);
    input.addEventListener("change", () => stageStack(item, input.value));
    addDetailField(fields, t("Количество"), input);
  }
  if (item.condition_editable && caps.edit_durability) {
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "100";
    input.step = "0.1";
    input.value = String(((state.durability.get(item.handle) ?? item.condition) * 100).toFixed(1));
    input.addEventListener("change", () => stageDurability(item, input.value));
    addDetailField(fields, t("Состояние"), input);
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
    select.title = t("Экспериментальная функция. Перед изменениями создаётся резервная копия.");
    select.addEventListener("change", () => {
      const [placementType, rawSlot] = select.value.split(":");
      const slotId = rawSlot === undefined ? null : Number(rawSlot);
      if (placementType === item.placement_type && slotId === item.placement_slot) state.placements.delete(item.handle);
      else state.placements.set(item.handle, [placementType, slotId]);
      invalidate();
      renderReferenceEditor(state.snapshot);
    });
    addDetailField(fields, t("Размещение"), select);
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
        option.textContent = definition ? definition.name : t("Неизвестное улучшение");
        option.title = "";
        option.selected = effective.includes(key);
        select.append(option);
      }
      select.title = t("Экспериментальная функция. Перед изменениями создаётся резервная копия.");
      select.addEventListener("change", () => {
        const values = [...select.selectedOptions].map((option) => option.value);
        if (values.length === item.upgrades.length && values.every((key, index) => key === item.upgrades[index])) state.upgrades.delete(item.handle);
        else state.upgrades.set(item.handle, values);
        invalidate();
        renderReferenceEditor(state.snapshot);
      });
      addDetailField(fields, t("Улучшения"), select);
    } else {
      const evidence = document.createElement("div");
      evidence.className = "reference-readonly-detail";
      evidence.textContent = t("Улучшения доступны только для просмотра.");
      evidence.removeAttribute("title");
      fields.append(evidence);
    }
  }
  if (item.remove_editable && caps.remove_items) {
    const remove = document.createElement("button");
    remove.className = "reference-danger";
    remove.type = "button";
    remove.textContent = state.detach.has(item.handle) ? t("ОТМЕНИТЬ УДАЛЕНИЕ") : t("УДАЛИТЬ ПРЕДМЕТ");
    remove.disabled = !item.remove_editable;
    remove.title = t("Удалить предмет");
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

// S.T.A.L.K.E.R. 2 pays in coupons; the original trilogy uses roubles.
function currencySuffix(s) {
  return String(s?.release_id ?? "").startsWith("stalker2") ? t("куп.") : "₽";
}

function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("ru-RU") : String(value);
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
    setStatus(t("Количество должно быть целым числом 1…{0}", max), "error");
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
    setStatus(t("Состояние должно быть числом 0…100"), "error");
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
    select.title = t("Выбрать предмет");
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
    support.textContent = item.condition_editable || item.editable || item.placement_editable || item.upgrade_editable ? t("МОЖНО ИЗМЕНИТЬ") : t("ТОЛЬКО ЧТЕНИЕ");
    support.className = support.textContent === t("ТОЛЬКО ЧТЕНИЕ") ? "muted" : "";
    row.append(support);
    const action = document.createElement("td");
    action.textContent = item.remove_editable ? "…" : "—";
    row.append(action);
    return row;
  }) : [Object.assign(document.createElement("tr"), {
    innerHTML: t("<td colspan=\"8\" class=\"reference-empty\">Предметов не найдено.</td>"),
  })]));
  el("reference-item-count").textContent = t("Предметов: {0}", s.inventory_count ?? items.length);
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
    panel.textContent = t("Данные о персонаже и группировках недоступны для этого сохранения.");
    panel.hidden = false;
    return;
  }
  if (s.player_faction_editable && factions.length) {
    const select = document.createElement("select");
    for (const faction of factions) {
      const option = document.createElement("option");
      option.value = faction.key;
      option.textContent = faction.name === faction.key ? t("Группировка {0}", faction.numeric_id) : faction.name;
      option.title = "";
      option.selected = faction.numeric_id === s.player_faction_index || faction.key === state.playerFaction;
      select.append(option);
    }
    const button = document.createElement("button");
    button.className = "reference-secondary";
    button.type = "button";
    button.textContent = state.playerFaction === null ? t("ИЗМЕНИТЬ ГРУППИРОВКУ") : t("ГРУППИРОВКА*");
    button.addEventListener("click", () => {
      const current = factions.find((entry) => entry.numeric_id === s.player_faction_index)?.key;
      state.playerFaction = select.value === current ? null : select.value;
      invalidate();
      renderReferenceCharacter(s);
      renderReferenceReview();
    });
    addDetailField(panel, t("Игрок"), select);
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
    addDetailField(panel, relation.name ?? t("Группировка"), input);
  }
}

function renderReferenceSnapshot(s) {
  el("reference-game-count").textContent = t("1 сохранение");
  el("reference-preview-name").textContent = s.name;
  const previewMeta = el("reference-preview-meta");
  previewMeta.replaceChildren();
  for (const [index, line] of [
    t("Игра: {0}", s.format_title),
    t("Источник: локальное сохранение"),
    t("Размер: {0}", s.size_text),
    `${BROWSER_UI_COPY.integrity}: ${integrityLabel(s)}`,
  ].entries()) {
    if (index) previewMeta.append(document.createElement("br"));
    previewMeta.append(document.createTextNode(line));
  }
  previewMeta.title = "";
  el("reference-preview-status").textContent = integrityLabel(s).toUpperCase();
  el("reference-activity").textContent = t("Проанализирован {0}; исходный файл не изменён.", s.name);
  const caps = s.capabilities ?? {};
  const editable = Boolean(caps.edit_money || caps.edit_stacks || caps.edit_durability || caps.edit_placement || caps.edit_upgrades);
  el("reference-preview-capability").textContent = capabilityLabel(editable);
  el("reference-preview-capability").className = `reference-chip ${editable ? "success" : "warning"}`;
  el("reference-summary-money").innerHTML = t("ДЕНЬГИ<br>{0} {1}", formatMoney(s.money), currencySuffix(s));
  el("reference-summary-items").innerHTML = t("ПРЕДМЕТЫ<br>{0}", s.inventory_count ?? "—");
  el("reference-summary-equipment").innerHTML = t("ЭКИПИРОВКА<br>{0}", s.equipment_count ?? "—");
  el("reference-summary-condition").innerHTML = `${BROWSER_UI_COPY.integritySummary}<br>${integrityLabel(s)}`;
  el("reference-editor-breadcrumb").textContent = `${s.format_title}  ›  ${s.name}`;
  el("reference-editor-state").textContent = capabilityLabel(editable);
  el("reference-editor-state").className = `reference-chip ${editable ? "success" : "warning"}`;
  el("reference-money").textContent = t("ДЕНЬГИ  {0} {1}", formatMoney(s.money), currencySuffix(s));
  el("reference-money-input").value = String(s.money ?? 0);
  el("reference-money-input").disabled = !s.money_editable;
  el("reference-money-clear").disabled = state.money === null;
  el("reference-weight").textContent = t("ВЕС  — кг");
  el("reference-source").innerHTML = t("Источник<br>Локальный файл");
  el("reference-integrity").innerHTML = `${BROWSER_UI_COPY.integrity}<br>${integrityLabel(s)}`;
  el("reference-editor-capability").innerHTML = t("Статус<br>{0}", editable ? t("Можно изменять") : t("Только чтение"));
  el("reference-equipment-summary").textContent = t("{0} объектов оборудования · неподтверждённые данные нельзя изменить", s.equipment_count ?? 0);
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
  // The shared core translates its messages from the same locale file.
  py.FS.mkdirTree("/core/locales");
  py.FS.writeFile(`/core/locales/${currentLanguage()}.json`, catalogSource(), { encoding: "utf8" });
  py.runPython(`import os, sys; os.environ["STALKER_EDITOR_LANG"] = ${JSON.stringify(currentLanguage())}; sys.path.insert(0, "/core")`);
  globalThis.__oozDecompress = (stream, size) => ooz.decompress(stream, size);
  const bridge = py.pyimport("web_bridge");
  bridge.install_decoder(globalThis.__oozDecompress);
  state.py = py;
  state.bridge = bridge;
  state.catalogsReady = installCatalogs({ bridge });
  state.catalogsReady.catch(fail);
  el("file-input").disabled = false;
  setStatus(t("Редактор готов. Выбери локальное сохранение."));
  state.catalogsReady.then(
    () => { if (!state.snapshot) setStatus(t("Приложение готово. Открой локальный файл сохранения.")); },
    () => {},
  );
}

async function openFile(file) {
  if (!state.bridge || !state.catalogsReady) return;
  setStatus(t("Открытие сохранения…"), "busy");
  try {
    const bytesReady = file.arrayBuffer();
    await state.catalogsReady;
    const bytes = new Uint8Array(await bytesReady);
    const snapshot = JSON.parse(state.bridge.analyze(bytes, file.name));
    state.snapshot = snapshot;
    setSoundTheme(snapshot.release_id ?? snapshot.format_id);
    play("open");
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
    setStatus(t("Сохранение проверено; исходный файл не изменён"));
    setItemTechnicalDetails(snapshotItem(state.referenceSelectedHandle));
  } catch (error) {
    fail(error, "open");
  }
}

function invalidate() {
  if (state.prepared !== null) state.prepared = null;
  if (state.snapshot) {
    renderReferenceReview();
    el("reference-review-status").textContent = t("Изменения готовы к проверке; исходный файл не изменён.");
  }
}

function preview() {
  try {
    if (!state.snapshot || !state.bridge) throw new Error(t("Сначала открой сохранение"));
    setStatus(t("Проверка изменений и создание копии…"), "busy");
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
    el("reference-review-status").textContent = t("Копия проверена ({0}). Оригинальный файл пока не изменён.", result.size_text);
    setStatus(t("Проверка выполнена; можно скачать копию"));
    setTechnicalDetails(technicalDetails(t("SHA-256 копии: {0}", result.output_sha256)));
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
    play("save");
    setStatus(t("Сохранена проверенная копия {0}; исходный файл не изменён.", name));
    setTechnicalDetails(technicalDetails(t("SHA-256 копии: {0}", state.prepared.output_sha256)));
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
  setStatus(details.hidden ? t("Персонаж скрыт") : t("Данные о персонаже и группировках показаны."));
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
    el("technical-details-copy").textContent = t("Скопировано");
  } catch {
    const fallback = document.createElement("textarea");
    fallback.value = text;
    fallback.setAttribute("readonly", "");
    fallback.style.position = "fixed";
    fallback.style.opacity = "0";
    document.body.append(fallback);
    fallback.select();
    if (document.execCommand("copy")) {
      el("technical-details-copy").textContent = t("Скопировано");
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
    setStatus(t("Сумма должна быть целым числом 0…2 000 000 000"), "error");
    return;
  }
  state.money = value === state.snapshot.money ? null : value;
  invalidate();
  el("reference-money").textContent = t("ДЕНЬГИ  {0} {1}", formatMoney(value), currencySuffix(state.snapshot));
  el("reference-money-clear").disabled = state.money === null;
  setStatus(t("Баланс изменён в памяти; исходный файл не изменён"));
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
    setStatus(t("Количество должно быть целым числом 1…{0}", max), "error");
    return;
  }
  state.adds.set(key, quantity);
  invalidate();
  renderReferenceEditor(state.snapshot);
  setStatus(t("Добавлен предмет: {0}. Оригинальный файл пока не изменён.", definition?.name ?? t("из каталога")));
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
    if (copied) button.textContent = t("Скопировано");
    else button.textContent = t("Не удалось скопировать");
    setTimeout(() => { button.textContent = t("Копировать"); }, 1400);
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
