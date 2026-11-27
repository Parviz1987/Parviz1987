/* TST Trade service worker: makes the panel installable and opens it even with a weak connection.
   Pages and scripts: network first, the saved copy only when offline. Prices and forecasts (/api/) are never
   cached: an old price shown as current would be wrong, so offline the panel says the data cannot be loaded.
   v2 (2026-11-26): the network request skips the browser's own HTTP cache («no-cache»: ask the server, a short 304
   when nothing changed). Before, a browser could answer from an hours-old copy after a deploy and the owner saw the
   old site; a new version of this file also clears the old saved copies. */
const CACHE = "tst-shell-v2";
const SHELL = ["/", "/static/app.css", "/static/chart.js", "/static/panel.js", "/static/pwa.js",
  "/static/icons/icon-192.png"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: "no-cache" }))).catch(() => {}))
    .then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/") ||
      u.pathname === "/version" || u.pathname === "/login" || u.pathname === "/logout") return;
  // a page: the same request by its address (a navigation request cannot be copied with new options); redirects are
  // handed back to the browser as they are (/status -> /admin#sistem), exactly like the browser would do itself
  const req = e.request.mode === "navigate"
    ? new Request(u.href, { cache: "no-cache", redirect: "manual", credentials: "same-origin" })
    : new Request(e.request, { cache: "no-cache" });
  e.respondWith(fetch(req).then((r) => {
    if (r.ok && !r.redirected && r.type === "basic") { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.match(e.request, { ignoreSearch: true })));
});
