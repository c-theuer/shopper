// Serves the built SPA and proxies /api/* to the backend Cloud Run service.
// The backend only accepts IAM-authenticated callers, so on Cloud Run each
// proxied request carries an ID token minted from the metadata server.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const PORT = Number(process.env.PORT ?? 8080);
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";
const USE_ID_TOKEN = process.env.USE_ID_TOKEN === "true";
const DIST = join(import.meta.dirname, "dist");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".json": "application/json",
};

let cachedToken = { value: "", expiresAt: 0 };

async function idToken() {
  if (Date.now() < cachedToken.expiresAt) return cachedToken.value;
  const url =
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity" +
    `?audience=${encodeURIComponent(BACKEND_URL)}`;
  const res = await fetch(url, { headers: { "Metadata-Flavor": "Google" } });
  if (!res.ok) throw new Error(`metadata server returned ${res.status}`);
  // Tokens live for 1 hour; refresh well before expiry.
  cachedToken = { value: await res.text(), expiresAt: Date.now() + 45 * 60 * 1000 };
  return cachedToken.value;
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return chunks.length ? Buffer.concat(chunks) : undefined;
}

async function proxy(req, res) {
  const headers = { ...req.headers };
  delete headers.host;
  delete headers.connection;
  delete headers["content-length"];
  // Never forward the IAP-issued assertion or caller auth to the backend.
  delete headers.authorization;
  if (USE_ID_TOKEN) headers.authorization = `Bearer ${await idToken()}`;

  const upstream = await fetch(new URL(req.url, BACKEND_URL), {
    method: req.method,
    headers,
    body: ["GET", "HEAD"].includes(req.method) ? undefined : await readBody(req),
    redirect: "manual",
  });
  const outHeaders = Object.fromEntries(upstream.headers);
  delete outHeaders["content-encoding"];
  delete outHeaders["content-length"];
  res.writeHead(upstream.status, outHeaders);
  res.end(Buffer.from(await upstream.arrayBuffer()));
}

async function serveStatic(req, res) {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname));
  const file = join(DIST, path);
  try {
    if (!file.startsWith(DIST) || !extname(file)) throw new Error("spa route");
    const body = await readFile(file);
    res.writeHead(200, { "content-type": MIME[extname(file)] ?? "application/octet-stream" });
    res.end(body);
  } catch {
    // Unknown paths fall back to index.html so client-side routes work.
    res.writeHead(200, { "content-type": MIME[".html"], "cache-control": "no-cache" });
    res.end(await readFile(join(DIST, "index.html")));
  }
}

http
  .createServer(async (req, res) => {
    try {
      if (req.url.startsWith("/api/")) await proxy(req, res);
      else await serveStatic(req, res);
    } catch (err) {
      console.error(err);
      if (!res.headersSent) res.writeHead(502, { "content-type": "text/plain" });
      res.end("Bad gateway");
    }
  })
  .listen(PORT, () => console.log(`frontend listening on ${PORT}`));
