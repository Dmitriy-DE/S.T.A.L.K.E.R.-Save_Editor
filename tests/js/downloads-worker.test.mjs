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

test("diagnostics objects remain unreadable", async () => {
  const response = await worker.fetch(
    new Request("https://downloads.example/diagnostics/report.log.gz"),
    { BUCKET: { async get() { throw new Error("must not read diagnostics"); } } },
    {},
  );

  assert.equal(response.status, 404);
});
