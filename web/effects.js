import { GameAudio, normalizeFamily } from "./game_audio.js";
import { currentLanguage, LANGUAGES, savedLanguage, setSavedLanguage, t } from "./i18n.js";

const KEYS = { sound: "se-sound", motion: "se-motion" };
const state = { sound: true, motion: true, theme: "soc", context: null };
export const gameAudio = new GameAudio();

function read(key, fallback) {
  try {
    const value = globalThis.localStorage?.getItem(key);
    return value === null || value === undefined ? fallback : value === "1";
  } catch { return fallback; }
}

function write(key, value) {
  try { globalThis.localStorage?.setItem(key, value ? "1" : "0"); } catch { /* session only */ }
}

const TONES = {
  stalker2: {
    square: false, base: 520,
    click: [[1.5, 0.035]], tab: [[1, 0.05], [1.26, 0.06]], open: [[0.75, 0.07], [1, 0.07], [1.5, 0.1]],
    save: [[1.5, 0.08], [2, 0.14]], error: [[0.5, 0.12], [0.42, 0.16]],
  },
  xray: {
    square: true, base: 1100,
    click: [[1, 0.025]], tab: [[0.8, 0.035], [1.2, 0.045]], open: [[0.5, 0.05], [0.75, 0.05], [1, 0.08]],
    save: [[0.8, 0.06], [1.2, 0.12]], error: [[0.2, 0.18]],
  },
};
const PITCH = { soc: 1, clear_sky: 0.92, cop: 1.08 };

export function soundTheme(release) {
  return normalizeFamily(release);
}

export function setSoundTheme(release) {
  state.theme = soundTheme(release);
  gameAudio.setFamily(state.theme);
}

function playTone(event) {
  const AudioContext = globalThis.AudioContext ?? globalThis.webkitAudioContext;
  if (!AudioContext) return;
  try {
    state.context ??= new AudioContext();
    const ctx = state.context;
    const table = state.theme === "stalker2" ? TONES.stalker2 : TONES.xray;
    const segments = table[event];
    if (!segments) return;
    const base = table.base * (state.theme === "stalker2" ? 1 : PITCH[state.theme] ?? 1);
    let at = ctx.currentTime;
    for (const [ratio, seconds] of segments) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = table.square ? "square" : "sine";
      osc.frequency.value = base * ratio;
      // Quiet by design: UI cues stay under the game's own menu volume.
      const peak = table.square ? 0.035 : 0.08;
      gain.gain.setValueAtTime(0, at);
      gain.gain.linearRampToValueAtTime(peak, at + 0.004);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + seconds);
      osc.connect(gain).connect(ctx.destination);
      osc.start(at);
      osc.stop(at + seconds + 0.01);
      at += seconds;
    }
  } catch { /* sound is decoration only */ }
}

export function play(event) {
  if (!state.sound) return;
  if (gameAudio.playEvent(event)) {
    return;
  }
  playTone(event);
}

export function fadeIn(element) {
  if (!state.motion || !element) return;
  element.classList.remove("is-entering");
  void element.offsetWidth;
  element.classList.add("is-entering");
}

function syncToggle(id, kind, enabled) {
  const button = globalThis.document?.getElementById(id);
  if (!button) return;
  button.setAttribute("aria-pressed", String(enabled));
  const img = button.querySelector("img");
  if (img) img.src = `assets/ui/shell_icons/${kind}-${enabled ? "on" : "off"}.svg`;
  button.title = kind === "sound"
    ? (enabled ? t("Звуки интерфейса: включены") : t("Звуки интерфейса: выключены"))
    : (enabled ? t("Анимации: включены") : t("Анимации: выключены"));
  const check = globalThis.document?.getElementById(`${kind}-check`);
  if (check) check.checked = enabled;
}

function apply() {
  globalThis.document?.documentElement.classList.toggle("no-motion", !state.motion);
  syncToggle("sound-toggle", "sound", state.sound);
  syncToggle("motion-toggle", "motion", state.motion);
}

export function setSound(enabled) {
  state.sound = Boolean(enabled);
  gameAudio.setSoundEnabled(state.sound);
  write(KEYS.sound, state.sound);
  apply();
  play("click");
}

export function setMotion(enabled) {
  state.motion = Boolean(enabled);
  write(KEYS.motion, state.motion);
  apply();
}

export function initEffects() {
  const reduced = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
  state.sound = read(KEYS.sound, true);
  state.motion = read(KEYS.motion, !reduced);
  gameAudio.setSoundEnabled(state.sound);
  gameAudio.setFamily(state.theme);
  const doc = globalThis.document;
  if (!doc) return;
  doc.getElementById("sound-toggle")?.addEventListener("click", () => setSound(!state.sound));
  doc.getElementById("motion-toggle")?.addEventListener("click", () => setMotion(!state.motion));
  doc.getElementById("sound-check")?.addEventListener("change", (event) => setSound(event.target.checked));
  doc.getElementById("motion-check")?.addEventListener("change", (event) => setMotion(event.target.checked));
  const select = doc.getElementById("language-select");
  if (select) {
    for (const [code, name] of Object.entries(LANGUAGES)) {
      const option = doc.createElement("option");
      option.value = code;
      option.textContent = name;
      select.append(option);
    }
    select.value = savedLanguage() ?? "";
    select.addEventListener("change", () => {
      setSavedLanguage(select.value || null);
      if ((select.value || null) !== currentLanguage()) globalThis.location?.reload();
    });
  }
  let lastHover = null;
  doc.addEventListener("mouseover", (event) => {
    const el = event.target?.closest?.("button, .reference-game, .reference-nav-button, .reference-footer-action, #reference-save-table tr");
    if (!el || el === lastHover || el.disabled) return;
    lastHover = el;
    play("hover");
  });
  doc.addEventListener("click", (event) => {
    gameAudio.handleUserInteraction();
    const button = event.target?.closest?.("button");
    if (!button || button.disabled || button.classList.contains("effect-toggle")) return;
    play(button.classList.contains("reference-nav-button") ? "tab" : "click");
  });
  apply();
}
