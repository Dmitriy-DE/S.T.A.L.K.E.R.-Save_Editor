// Public read-only file server for the save-editor binary downloads.
// Serves objects from the R2 bucket bound as BUCKET, so the private code repo
// stays private while release binaries are publicly downloadable.
export default {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", { status: 405 });
    }
    const key = decodeURIComponent(new URL(request.url).pathname.slice(1));
    if (!key) {
      return new Response("save-editor downloads\n", {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    const object = await env.BUCKET.get(key);
    if (object === null) {
      return new Response("Not found", { status: 404 });
    }
    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("etag", object.httpEtag);
    headers.set("cache-control", "public, max-age=3600");
    headers.set("content-disposition", `attachment; filename="${key.split("/").pop()}"`);
    return new Response(request.method === "HEAD" ? null : object.body, { headers });
  },
};
