/* Iris-Stego Lab — service worker (offline app shell) */
const CACHE = "iris-stego-v2";
const SHELL = [
  "/",
  "/index.html",
  "/style.css",
  "/app.js",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png",
  "/favicon.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);

  // Never touch the API or non-GET (POST uploads, form posts) — always live.
  if (req.method !== "GET" || url.pathname.startsWith("/api/")) return;

  // HTML navigations: network-first, cache fallback offline.
  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((res) => { caches.open(CACHE).then((c) => c.put("/", res.clone())); return res; })
        .catch(() => caches.match("/").then((r) => r || caches.match("/index.html")))
    );
    return;
  }

  // Everything else (app.js, style.css, icons): network-first so updates always
  // land when online; fall back to cache only when offline.
  e.respondWith(
    fetch(req)
      .then((res) => { caches.open(CACHE).then((c) => c.put(req, res.clone())); return res; })
      .catch(() => caches.match(req))
  );
});
