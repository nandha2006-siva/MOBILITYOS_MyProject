const CACHE_NAME = "mobilityos-cache-v1";
const ASSETS = [
  "/",
  "/index.html",
  "/dashboard.html",
  "/manifest.json"
];

self.addEventListener("install", e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(ASSETS);
    })
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", e => {
  // Skip caching API calls and websockets
  if (e.request.url.includes("/api/") || e.request.url.includes("/ws/") || e.request.url.includes("maps.googleapis.com")) {
    return fetch(e.request);
  }
  
  e.respondWith(
    caches.match(e.request).then(response => {
      return response || fetch(e.request).catch(() => {
        if (e.request.mode === "navigate") {
          return caches.match("/dashboard.html");
        }
      });
    })
  );
});
