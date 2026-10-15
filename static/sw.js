/* KPN v3: cache static assets only. Never retain personalized HTML/API data. */
const CACHE_NAME = "kpn-cache-v3-state-quick-actions";
const OFFLINE_PAGE = "/static/offline.html";
const PRECACHE = [OFFLINE_PAGE, "/static/images/pwa-icon-192.png"];
self.addEventListener("install", event => {
    event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(PRECACHE)));
    self.skipWaiting();
});
self.addEventListener("activate", event => {
    event.waitUntil(caches.keys().then(names => Promise.all(
        names.filter(name => name.startsWith("kpn-cache-") && name !== CACHE_NAME)
            .map(name => caches.delete(name))
    )).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
    const request = event.request;
    const url = new URL(request.url);
    if (request.method !== "GET" || url.origin !== self.location.origin) return;
    if (request.mode === "navigate") {
        event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_PAGE)
            .then(page => page || new Response("You are offline. Reconnect to continue.",
                {status: 503, headers: {"Content-Type": "text/plain"}}))));
    } else if (url.pathname.startsWith("/static/")) {
        event.respondWith(caches.open(CACHE_NAME).then(async cache => {
            const cached = await cache.match(request);
            if (cached) return cached;
            const response = await fetch(request);
            if (response.ok && response.type === "basic"
                && new URL(response.url).pathname.startsWith("/static/")) {
                await cache.put(request, response.clone());
            }
            return response;
        }));
    }
    // API, account data, media uploads, third parties and mutations bypass caching.
});
