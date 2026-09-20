import assert from "node:assert/strict";
import test from "node:test";

import { installCatalogs, loadCoreResources } from "../../web/bootstrap.js";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function response({ json, text }) {
  return {
    ok: true,
    json: async () => json,
    text: async () => text,
  };
}

test("core resources start concurrently and leave catalogs deferred", async () => {
  const decoder = deferred();
  const pyodideModule = deferred();
  const sources = deferred();
  const bridgeSource = deferred();
  const started = [];
  const fakePyodide = { FS: {} };

  const coreReady = loadCoreResources({
    importModule(url) {
      started.push(`import:${url}`);
      return url === "ooz.js" ? decoder.promise : pyodideModule.promise;
    },
    fetchResource(url) {
      started.push(`fetch:${url}`);
      if (url === "pysrc.json") return sources.promise;
      if (url === "web_bridge.py") return bridgeSource.promise;
      throw new Error(`unexpected core fetch: ${url}`);
    },
    oozUrl: "ooz.js",
    pyodideUrl: "pyodide/",
  });

  assert.deepEqual(started, [
    "import:ooz.js",
    "import:pyodide/pyodide.mjs",
    "fetch:pysrc.json",
    "fetch:web_bridge.py",
  ]);
  assert.equal(started.some((entry) => entry.includes("catalogs.json")), false);

  decoder.resolve({ decompress() {} });
  pyodideModule.resolve({
    loadPyodide: async ({ indexURL }) => {
      assert.equal(indexURL, "pyodide/");
      return fakePyodide;
    },
  });
  sources.resolve(response({ json: { files: {}, source_sha256: "abc" } }));
  bridgeSource.resolve(response({ text: "bridge source" }));

  assert.deepEqual(await coreReady, {
    bridgeSource: "bridge source",
    bundle: { files: {}, source_sha256: "abc" },
    ooz: { decompress: (await decoder.promise).decompress },
    py: fakePyodide,
  });
});

test("catalog installation is a separate awaited operation", async () => {
  const catalogResponse = deferred();
  const installed = [];
  const bridge = {
    install_catalogs(payload) {
      installed.push(payload);
    },
  };
  let settled = false;

  const catalogsReady = installCatalogs({
    bridge,
    fetchResource(url) {
      assert.equal(url, "catalogs.json");
      return catalogResponse.promise;
    },
  });
  catalogsReady.then(() => { settled = true; });
  await Promise.resolve();
  assert.equal(settled, false);
  assert.deepEqual(installed, []);

  catalogResponse.resolve(response({ text: '{"catalogs": []}' }));
  await catalogsReady;
  assert.deepEqual(installed, ['{"catalogs": []}']);
});
