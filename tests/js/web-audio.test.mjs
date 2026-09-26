import assert from "node:assert/strict";
import test from "node:test";

import { EVENT_FILES, GameAudio, MUSIC_FILES, normalizeFamily } from "../../web/game_audio.js";

function createMockAudioContext() {
  const decoded = [];
  return class MockAudioContext {
    constructor() {
      this.state = "running";
      this.destination = {};
      this.currentTime = 0;
    }
    async resume() {
      this.state = "running";
    }
    async decodeAudioData(arrayBuffer) {
      decoded.push(arrayBuffer);
      return { duration: 1.0, length: 44100, numberOfChannels: 2, sampleRate: 44100 };
    }
    createBufferSource() {
      return {
        buffer: null,
        connect() {},
        start() {},
        stop() {},
      };
    }
    createGain() {
      return {
        gain: { value: 1.0 },
        connect() {},
      };
    }
  };
}

function createMockAudioElement(instances = []) {
  return class MockAudio {
    constructor(src) {
      this.src = src;
      this.loop = false;
      this.volume = 1.0;
      this.paused = true;
      this.currentTime = 0;
      instances.push(this);
    }
    async play() {
      this.paused = false;
    }
    pause() {
      this.paused = true;
    }
  };
}

test("audio files are not loaded before first user interaction", async () => {
  const fetched = [];
  const audio = new GameAudio({
    basePath: "assets/sounds/game",
    fetchResource: async (url) => {
      fetched.push(url);
      return { ok: true, arrayBuffer: async () => new ArrayBuffer(8) };
    },
    AudioContextClass: createMockAudioContext(),
    AudioElementClass: createMockAudioElement(),
  });

  assert.equal(audio.userInteracted, false);
  assert.equal(fetched.length, 0);
  assert.equal(audio.isFamilyLoaded("soc"), false);
});

test("lazy loads only selected game audio after first user click", async () => {
  const fetched = [];
  const audioInstances = [];
  const audio = new GameAudio({
    basePath: "assets/sounds/game",
    fetchResource: async (url) => {
      fetched.push(url);
      return { ok: true, arrayBuffer: async () => new ArrayBuffer(8) };
    },
    AudioContextClass: createMockAudioContext(),
    AudioElementClass: createMockAudioElement(audioInstances),
  });

  audio.setFamily("cop");
  assert.equal(fetched.length, 0, "no fetch before interaction");

  await audio.handleUserInteraction();
  assert.equal(audio.userInteracted, true);

  await audio.loadingPromises.get("cop");

  assert.equal(audio.isFamilyLoaded("cop"), true);
  assert.equal(audio.isFamilyLoaded("soc"), false);
  assert.equal(audio.isFamilyLoaded("clear_sky"), false);

  // All cop event files should be fetched
  const expectedEvents = Object.values(EVENT_FILES).map((f) => `assets/sounds/game/cop/${f}`);
  for (const exp of expectedEvents) {
    assert.ok(fetched.includes(exp), `expected ${exp} in fetched`);
  }
  // No other families fetched
  assert.ok(fetched.every((f) => f.includes("/cop/")));

  // CoP menu music should be playing
  assert.equal(audioInstances.length, 1);
  assert.equal(audioInstances[0].src, "assets/sounds/game/cop/menu.ogg");
  assert.equal(audioInstances[0].paused, false);
});

test("switching game family loads new family audio and stops old music", async () => {
  const fetched = [];
  const audioInstances = [];
  const audio = new GameAudio({
    basePath: "assets/sounds/game",
    fetchResource: async (url) => {
      fetched.push(url);
      return { ok: true, arrayBuffer: async () => new ArrayBuffer(8) };
    },
    AudioContextClass: createMockAudioContext(),
    AudioElementClass: createMockAudioElement(audioInstances),
  });

  audio.setFamily("soc");
  await audio.handleUserInteraction();
  await audio.loadingPromises.get("soc");

  assert.equal(audio.isFamilyLoaded("soc"), true);
  assert.equal(audio.isFamilyLoaded("clear_sky"), false);
  const socMusic = audioInstances[0];
  assert.equal(socMusic.src, "assets/sounds/game/soc/wasteland2_l.ogg");
  assert.equal(socMusic.paused, false);

  // Switch to Clear Sky
  await audio.setFamily("clear_sky");
  await audio.loadingPromises.get("clear_sky");

  assert.equal(socMusic.paused, true, "SoC music should be paused/stopped");
  assert.equal(audio.isFamilyLoaded("clear_sky"), true);
  const csMusic = audioInstances[1];
  assert.equal(csMusic.src, "assets/sounds/game/clear_sky/wasteland2.ogg");
  assert.equal(csMusic.paused, false);
});

test("sound toggle disables audio playback and stops music", async () => {
  const fetched = [];
  const audioInstances = [];
  const audio = new GameAudio({
    basePath: "assets/sounds/game",
    fetchResource: async (url) => {
      fetched.push(url);
      return { ok: true, arrayBuffer: async () => new ArrayBuffer(8) };
    },
    AudioContextClass: createMockAudioContext(),
    AudioElementClass: createMockAudioElement(audioInstances),
  });

  audio.setFamily("cop");
  await audio.handleUserInteraction();
  await audio.loadingPromises.get("cop");

  const music = audioInstances[0];
  assert.equal(music.paused, false);

  // Disable sound
  audio.setSoundEnabled(false);
  assert.equal(audio.soundEnabled, false);
  assert.equal(music.paused, true);
  assert.equal(audio.playEvent("click"), false);

  // Re-enable sound
  audio.setSoundEnabled(true);
  assert.equal(audio.soundEnabled, true);
  assert.equal(audioInstances[1].paused, false, "music resumes when enabled");
});

test("normalizeFamily maps releases to trilogy families and stalker2", () => {
  assert.equal(normalizeFamily("soc"), "soc");
  assert.equal(normalizeFamily("shoc"), "soc");
  assert.equal(normalizeFamily("Shadow of Chornobyl"), "soc");
  assert.equal(normalizeFamily("cs"), "clear_sky");
  assert.equal(normalizeFamily("clear_sky"), "clear_sky");
  assert.equal(normalizeFamily("cop"), "cop");
  assert.equal(normalizeFamily("Call of Pripyat"), "cop");
  assert.equal(normalizeFamily("stalker2"), "stalker2");
  assert.equal(normalizeFamily("s2"), "stalker2");
});
