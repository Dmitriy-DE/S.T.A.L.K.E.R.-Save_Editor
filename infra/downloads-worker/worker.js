// Public file server for save-editor downloads and opt-in diagnostics intake.
// Serves objects from the R2 bucket bound as BUCKET, so the private code repo
// stays private while release binaries are publicly downloadable.
const MAX_DIAGNOSTIC_BYTES = 2 * 1024 * 1024;
const DIAGNOSTIC_RATE_LIMIT_KEY = "diagnostics";

function jsonResponse(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

async function checkDiagnosticsRateLimit(env) {
  const limiter = env.DIAGNOSTICS_RATE_LIMITER;
  if (!limiter || typeof limiter.limit !== "function") {
    return 503;
  }
  try {
    const result = await limiter.limit({ key: DIAGNOSTIC_RATE_LIMIT_KEY });
    return result.success ? null : 429;
  } catch {
    return 503;
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/diagnostics") {
      if (request.method !== "POST") {
        return new Response("Method Not Allowed", { status: 405 });
      }
      const contentType = (request.headers.get("content-type") || "").split(";", 1)[0].toLowerCase();
      const declaredLength = Number(request.headers.get("content-length") || "0");
      if (contentType !== "application/gzip") {
        return new Response("Diagnostics payload must be application/gzip", { status: 415 });
      }
      if (declaredLength > MAX_DIAGNOSTIC_BYTES) {
        return new Response("Diagnostics payload is too large", { status: 413 });
      }
      const rateLimitStatus = await checkDiagnosticsRateLimit(env);
      if (rateLimitStatus === 429) {
        return new Response("Diagnostics rate limit exceeded", { status: 429 });
      }
      if (rateLimitStatus !== null) {
        return new Response("Diagnostics service is not configured", { status: 503 });
      }
      const body = await request.arrayBuffer();
      if (body.byteLength === 0 || body.byteLength > MAX_DIAGNOSTIC_BYTES) {
        return new Response("Diagnostics payload is too large or empty", { status: 413 });
      }
      const reportId = crypto.randomUUID();
      const key = `diagnostics/${new Date().toISOString().replace(/[:.]/g, "-")}-${reportId}.log.gz`;
      await env.BUCKET.put(key, body, {
        httpMetadata: {
          contentType: "application/gzip",
          cacheControl: "private, no-store",
        },
        customMetadata: {
          reportId,
          source: "save-editor-desktop",
        },
      });
      return jsonResponse({ report_id: reportId }, 201);
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", { status: 405 });
    }
    const key = decodeURIComponent(url.pathname.slice(1));
    if (!key) {
      return new Response("save-editor downloads\n", {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    if (key.startsWith("diagnostics/")) {
      return new Response("Not found", { status: 404 });
    }
    const object = await env.BUCKET.get(key);
    if (object === null) {
      return new Response("Not found", { status: 404 });
    }
    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("etag", object.httpEtag);
    const manifest = key === "latest.json";
    headers.set(
      "cache-control",
      manifest ? "public, max-age=60, must-revalidate" : "public, max-age=31536000, immutable",
    );
    if (manifest) {
      headers.set("content-type", "application/json; charset=utf-8");
      headers.set("content-disposition", "inline");
    } else {
      headers.set("content-disposition", `attachment; filename="${key.split("/").pop()}"`);
    }
    return new Response(request.method === "HEAD" ? null : object.body, { headers });
  },
};
