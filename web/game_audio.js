// Real menu sounds and menu music for the web build, mirroring ui/game_audio.py.
// Lazy-loads the selected game family's audio files after first user interaction.

export const EVENT_FILES = {
  click: "menu_accept.ogg",
  tab: "menu_switch.ogg",
  hover: "menu_select.ogg",
  error: "menu_decline.ogg",
  open: "inv_open.ogg",
  save: "inv_slot.ogg",
};

export const MUSIC_FILES = {
  cop: "menu.ogg",
  clear_sky: "wasteland2.ogg",
  soc: "wasteland2_l.ogg",
};

export const FAMILIES = new Set(["cop", "clear_sky", "soc"]);

export function normalizeFamily(releaseOrFamily) {
  const value = String(releaseOrFamily ?? "").toLowerCase();
  if (value.startsWith("stalker2") || value === "s2") return "stalker2";
  if (value.includes("cop") || value.includes("pripyat")) return "cop";
  if (value.includes("cs") || value.includes("clear")) return "clear_sky";
  if (value.includes("soc") || value.includes("shoc") || value.includes("shadow")) return "soc";
  return "soc";
}

export class GameAudio {
  constructor({
    basePath = "assets/sounds/game",
    fetchResource = globalThis.fetch,
    AudioContextClass = globalThis.AudioContext ?? globalThis.webkitAudioContext,
    AudioElementClass = globalThis.Audio,
  } = {}) {
    this.basePath = basePath;
    this.fetchResource = fetchResource;
    this.AudioContextClass = AudioContextClass;
    this.AudioElementClass = AudioElementClass;
    this.family = "soc";
    this.userInteracted = false;
    this.soundEnabled = true;
    this.loadedFamilies = new Set();
    this.loadingPromises = new Map();
    this.audioBuffers = new Map(); // `${family}:${event}` -> AudioBuffer
    this.context = null;
    this.musicElement = null;
    this.currentMusicFamily = null;
  }

  ensureContext() {
    if (!this.context && this.AudioContextClass) {
      try {
        this.context = new this.AudioContextClass();
      } catch {
        /* audio context might fail in non-standard environment */
      }
    }
    if (this.context && this.context.state === "suspended") {
      this.context.resume().catch(() => {});
    }
    return this.context;
  }

  isFamilyLoaded(family) {
    return this.loadedFamilies.has(family);
  }

  async loadFamily(family) {
    if (!FAMILIES.has(family)) return;
    if (this.loadedFamilies.has(family)) return;
    if (this.loadingPromises.has(family)) {
      return this.loadingPromises.get(family);
    }

    const promise = (async () => {
      const ctx = this.ensureContext();
      const events = Object.entries(EVENT_FILES);
      await Promise.all(
        events.map(async ([event, filename]) => {
          const url = `${this.basePath}/${family}/${filename}`;
          try {
            if (this.fetchResource && ctx) {
              const resp = await this.fetchResource(url);
              if (resp && (resp.ok || resp.status === 200)) {
                const arrayBuf = await resp.arrayBuffer();
                const audioBuf = await ctx.decodeAudioData(arrayBuf);
                this.audioBuffers.set(`${family}:${event}`, audioBuf);
              }
            }
          } catch {
            // Individual decode failure falls back to tone
          }
        })
      );
      this.loadedFamilies.add(family);
    })();

    this.loadingPromises.set(family, promise);
    return promise;
  }

  async handleUserInteraction() {
    if (!this.userInteracted) {
      this.userInteracted = true;
      this.ensureContext();
      if (FAMILIES.has(this.family)) {
        await this.loadFamily(this.family);
        if (this.soundEnabled) {
          this.playMusic(this.family);
        }
      }
    }
  }

  async setFamily(releaseOrFamily) {
    const newFamily = normalizeFamily(releaseOrFamily);
    if (newFamily === this.family && this.currentMusicFamily === newFamily) {
      return;
    }
    this.family = newFamily;
    if (this.userInteracted) {
      if (FAMILIES.has(newFamily)) {
        await this.loadFamily(newFamily);
        if (this.soundEnabled && this.family === newFamily) {
          this.playMusic(newFamily);
        }
      } else {
        this.stopMusic();
      }
    }
  }

  setSoundEnabled(enabled) {
    this.soundEnabled = Boolean(enabled);
    if (!this.soundEnabled) {
      this.stopMusic();
    } else if (this.userInteracted && FAMILIES.has(this.family)) {
      this.playMusic(this.family);
    }
  }

  playMusic(family) {
    if (!this.soundEnabled || !this.userInteracted) return;
    if (!FAMILIES.has(family)) {
      this.stopMusic();
      return;
    }
    if (this.currentMusicFamily === family && this.musicElement && !this.musicElement.paused) {
      return;
    }
    this.stopMusic();
    const musicFile = MUSIC_FILES[family];
    if (!musicFile) return;

    const url = `${this.basePath}/${family}/${musicFile}`;
    if (this.AudioElementClass) {
      try {
        const audio = new this.AudioElementClass(url);
        audio.loop = true;
        audio.volume = 0.25;
        const playPromise = audio.play();
        if (playPromise && typeof playPromise.catch === "function") {
          playPromise.catch(() => {});
        }
        this.musicElement = audio;
        this.currentMusicFamily = family;
      } catch {
        /* audio element creation/play failed */
      }
    }
  }

  stopMusic() {
    if (this.musicElement) {
      try {
        this.musicElement.pause();
        this.musicElement.currentTime = 0;
      } catch {}
      this.musicElement = null;
    }
    this.currentMusicFamily = null;
  }

  playEvent(event) {
    if (!this.soundEnabled) return false;
    this.handleUserInteraction();

    const ctx = this.ensureContext();
    const buffer = this.audioBuffers.get(`${this.family}:${event}`);
    if (ctx && buffer) {
      try {
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        const gain = ctx.createGain();
        gain.gain.value = 0.6;
        source.connect(gain).connect(ctx.destination);
        source.start(0);
        return true;
      } catch {
        return false;
      }
    }
    return false;
  }
}
