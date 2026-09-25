// Interface translations shared with the desktop app: locales/<code>.json maps
// the Russian source text to the translation (plurals: "one|few|many" → list).

export const LANGUAGES = {
  ru: "Русский",
  uk: "Українська",
  en: "English",
  de: "Deutsch",
  fr: "Français",
  it: "Italiano",
  es: "Español",
  pl: "Polski",
  cs: "Čeština",
  pt_BR: "Português (Brasil)",
  tr: "Türkçe",
  ja: "日本語",
  ko: "한국어",
  zh_CN: "简体中文",
  zh_TW: "繁體中文",
};

const STORAGE_KEY = "se-language";
let language = "ru";
let catalog = {};
let catalogText = "{}";

function storageGet(key) {
  try { return globalThis.localStorage?.getItem(key) ?? null; } catch { return null; }
}

function storageSet(key, value) {
  try {
    if (value === null) globalThis.localStorage?.removeItem(key);
    else globalThis.localStorage?.setItem(key, value);
  } catch { /* private mode: the choice lasts for this page only */ }
}

export function normalizeLanguage(code) {
  if (!code) return null;
  const value = String(code).replace("-", "_");
  if (value in LANGUAGES) return value;
  const lowered = value.toLowerCase();
  for (const known of Object.keys(LANGUAGES)) if (known.toLowerCase() === lowered) return known;
  if (lowered.startsWith("zh")) return /(tw|hk|hant)$/.test(lowered) ? "zh_TW" : "zh_CN";
  if (lowered.startsWith("pt")) return "pt_BR";
  const base = lowered.split("_")[0];
  return base in LANGUAGES ? base : null;
}

export function savedLanguage() {
  return normalizeLanguage(storageGet(STORAGE_KEY));
}

export function preferredLanguage() {
  const saved = savedLanguage();
  if (saved) return saved;
  for (const candidate of globalThis.navigator?.languages ?? [globalThis.navigator?.language]) {
    const found = normalizeLanguage(candidate);
    if (found) return found;
  }
  return "en";
}

export function setSavedLanguage(code) {
  storageSet(STORAGE_KEY, code ? normalizeLanguage(code) : null);
}

export async function initI18n({ fetchResource = globalThis.fetch?.bind(globalThis), code } = {}) {
  language = normalizeLanguage(code) ?? preferredLanguage();
  catalog = {};
  catalogText = "{}";
  if (language !== "ru" && fetchResource) {
    try {
      const response = await fetchResource(`locales/${language}.json`);
      if (response.ok) {
        catalogText = await response.text();
        catalog = JSON.parse(catalogText);
      }
    } catch {
      catalog = {};
    }
  }
  if (globalThis.document?.documentElement) {
    globalThis.document.documentElement.lang = language.replace("_", "-");
  }
  return language;
}

export function currentLanguage() {
  return language;
}

export function catalogSource() {
  return catalogText;
}

function format(text, args) {
  return args.length
    ? text.replace(/\{(\d+)\}/g, (match, index) => (index < args.length ? String(args[index]) : match))
    : text;
}

export function t(text, ...args) {
  const value = language === "ru" ? null : catalog[text];
  return format(typeof value === "string" && value ? value : String(text), args);
}

function pluralIndex(code, count) {
  const n = Math.abs(Math.trunc(Number(count) || 0));
  if (code === "ru" || code === "uk") {
    if (n % 10 === 1 && n % 100 !== 11) return 0;
    if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return 1;
    return 2;
  }
  if (code === "pl") {
    if (n === 1) return 0;
    if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return 1;
    return 2;
  }
  if (code === "cs") return n === 1 ? 0 : n >= 2 && n <= 4 ? 1 : 2;
  if (["ja", "ko", "zh_CN", "zh_TW", "tr"].includes(code)) return 0;
  if (code === "fr" || code === "pt_BR") return n <= 1 ? 0 : 1;
  return n === 1 ? 0 : 1;
}

export function tn(count, one, few, many) {
  let forms = [one, few, many];
  let code = language;
  if (language !== "ru") {
    const value = catalog[`${one}|${few}|${many}`];
    if (Array.isArray(value) && value.length) forms = value;
    else code = "ru";
  }
  return forms[Math.min(pluralIndex(code, count), forms.length - 1)];
}

const ATTRIBUTES = ["placeholder", "title", "aria-label", "alt"];

// Translate the static markup once: text nodes and a few attributes whose
// Russian source text has an entry in the catalog.
export function translateDom(root = globalThis.document?.body) {
  if (!root || language === "ru") return;
  const doc = root.ownerDocument ?? globalThis.document;
  const walker = doc.createTreeWalker(root, 4 /* NodeFilter.SHOW_TEXT */);
  const nodes = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node);
  for (const node of nodes) {
    const raw = node.nodeValue;
    const trimmed = raw.trim();
    if (!trimmed) continue;
    const value = catalog[trimmed];
    if (typeof value === "string" && value) node.nodeValue = raw.replace(trimmed, value);
  }
  for (const element of root.querySelectorAll("*")) {
    for (const name of ATTRIBUTES) {
      const value = element.getAttribute(name);
      const translated = value ? catalog[value.trim()] : null;
      if (typeof translated === "string" && translated) element.setAttribute(name, translated);
    }
  }
  const title = doc.title && catalog[doc.title];
  if (typeof title === "string" && title) doc.title = title;
}
