import assert from "node:assert/strict";
import test from "node:test";

import worker from "../../infra/downloads-worker/worker.js";

const endpoint = "https://downloads.example/diagnostics";

function request(body = new Uint8Array([1])) {
  return new Request(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/gzip",
      "content-length": String(body.byteLength),
    },
    body,
  });
}

function requestWithoutLength(body) {
  return new Request(endpoint, {
    method: "POST",
    headers: { "content-type": "application/gzip" },
    body,
  });
}

function bucket() {
  return {
    puts: [],
    lists: 0,
    deletes: 0,
    async put(key, body) {
      this.puts.push({ key, body });
    },
    async list() {
      this.lists += 1;
      throw new Error("POST must not list diagnostics");
    },
    async delete() {
      this.deletes += 1;
      throw new Error("POST must not delete diagnostics");
    },
  };
}

function context() {
  return { waitUntil() {} };
}

test("diagnostics refuses deployment without its rate-limit binding", async () => {
  const response = await worker.fetch(request(), { BUCKET: bucket() }, context());

  assert.equal(response.status, 503);
});

test("diagnostics rate limit rejects before writing to R2", async () => {
  const storage = bucket();
  const env = {
    BUCKET: storage,
    DIAGNOSTICS_RATE_LIMITER: {
      async limit({ key }) {
        assert.equal(key, "diagnostics");
        return { success: false };
      },
    },
  };

  const response = await worker.fetch(request(), env, context());

  assert.equal(response.status, 429);
  assert.deepEqual(storage.puts, []);
});

test("diagnostics stores bounded payload without listing or deleting", async () => {
  const storage = bucket();
  const env = {
    BUCKET: storage,
    DIAGNOSTICS_RATE_LIMITER: { async limit() { return { success: true }; } },
  };

  const response = await worker.fetch(request(), env, { waitUntil() {} });

  assert.equal(response.status, 201);
  assert.equal(storage.puts.length, 1);
  assert.equal(storage.lists, 0);
  assert.equal(storage.deletes, 0);
});

test("diagnostics bounds chunked bodies before writing to R2", async () => {
  const storage = bucket();
  const env = {
    BUCKET: storage,
    DIAGNOSTICS_RATE_LIMITER: { async limit() { return { success: true }; } },
  };
  const response = await worker.fetch(
    requestWithoutLength(new Uint8Array(2 * 1024 * 1024 + 1)),
    env,
    context(),
  );

  assert.equal(response.status, 413);
  assert.deepEqual(storage.puts, []);
});

test("diagnostics objects remain unreadable", async () => {
  const response = await worker.fetch(
    new Request("https://downloads.example/diagnostics/report.log.gz"),
    { BUCKET: { async get() { throw new Error("must not read diagnostics"); } } },
    {},
  );

  assert.equal(response.status, 404);
});

test("diagnostics errors use a JSON no-store contract", async () => {
  const cases = [
    [new Request(endpoint, { method: "GET" }), {}, 405],
    [request(new Uint8Array([1])), { BUCKET: bucket() }, 503],
    [
      new Request(endpoint, {
        method: "POST",
        headers: {
          "content-type": "text/plain",
          "content-length": "1",
        },
        body: new Uint8Array([1]),
      }),
      { BUCKET: bucket(), DIAGNOSTICS_RATE_LIMITER: { async limit() { return { success: true }; } } },
      415,
    ],
  ];

  for (const [input, env, expectedStatus] of cases) {
    const response = await worker.fetch(input, env, context());
    assert.equal(response.status, expectedStatus);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.equal(response.headers.get("content-type"), "application/json; charset=utf-8");
    const body = await response.json();
    assert.equal(typeof body.error, "string");
  }
});

test("diagnostics storage failures return a bounded no-store error", async () => {
  const response = await worker.fetch(request(), {
    BUCKET: {
      async put() {
        throw new Error("private storage detail");
      },
    },
    DIAGNOSTICS_RATE_LIMITER: { async limit() { return { success: true }; } },
  }, context());

  assert.equal(response.status, 503);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), { error: "Diagnostics storage unavailable" });
});
