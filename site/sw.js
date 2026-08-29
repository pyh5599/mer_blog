const SHELL = "shell-v1";
const DATA = "data-v1";
const SHELL_FILES = ["./", "./index.html", "./app.js", "./style.css", "./manifest.webmanifest", "./icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => ![SHELL, DATA].includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.endsWith(".mp3")) return; // stream directly, never cache
  if (url.pathname.endsWith(".json")) {
    // network first, cache fallback
    e.respondWith(
      fetch(e.request)
        .then((r) => { const copy = r.clone(); caches.open(DATA).then((c) => c.put(e.request, copy)); return r; })
        .catch(() => caches.match(e.request))
    );
    return;
  }
  // shell: network first so updates land, cache fallback offline
  e.respondWith(fetch(e.request).then((r) => { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(e.request, copy)); return r; }).catch(() => caches.match(e.request)));
});
