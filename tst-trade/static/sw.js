/* TST Trade service worker: makes the panel installable and opens it even with a weak connection.
   Pages and scripts: network first, the saved copy only when offline. Prices and forecasts (/api/) are never
   cached: an old price shown as current would be wrong, so offline the panel says the data cannot be loaded. */
const CACHE = "tst-shell-v1";
const SHELL = ["/", "/static/app.css", "/static/chart.js", "/static/panel.js", "/static/pwa.js",
  "/static/icons/icon-192.png"];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/") ||
      u.pathname === "/version" || u.pathname === "/login" || u.pathname === "/logout") return;
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok && !r.redirected) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.match(e.request, { ignoreSearch: true })));
});
