const CACHE = "kunal-stocks-v2";

const APP_SHELL = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys =>
        Promise.all(
          keys
            .filter(key => key !== CACHE)
            .map(key => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;

  if (request.method !== "GET") return;

  const url = new URL(request.url);

  /*
   * MARKET / IPO DATA
   *
   * Always request the newest version from GitHub Pages.
   * Cache is only a fallback if the network is unavailable.
   */
  if (
    url.pathname.endsWith("/data.json") ||
    url.pathname.endsWith("/ipo.json")
  ) {
    event.respondWith(
      fetch(request, {
        cache: "no-store"
      })
        .then(response => {
          if (response.ok) {
            const copy = response.clone();

            caches.open(CACHE).then(cache => {
              cache.put(request, copy);
            });
          }

          return response;
        })
        .catch(() => caches.match(request))
    );

    return;
  }

  /*
   * HTML / APP SHELL
   *
   * Network first.
   * This allows a newly deployed index.html to replace
   * the old cached version.
   */
  if (
    request.mode === "navigate" ||
    url.pathname.endsWith("/index.html")
  ) {
    event.respondWith(
      fetch(request, {
        cache: "no-store"
      })
        .then(response => {
          if (response.ok) {
            const copy = response.clone();

            caches.open(CACHE).then(cache => {
              cache.put("./index.html", copy);
            });
          }

          return response;
        })
        .catch(() => caches.match("./index.html"))
    );

    return;
  }

  /*
   * Other static assets.
   *
   * Network first, cached fallback.
   */
  event.respondWith(
    fetch(request)
      .then(response => {
        if (response.ok) {
          const copy = response.clone();

          caches.open(CACHE).then(cache => {
            cache.put(request, copy);
          });
        }

        return response;
      })
      .catch(() => caches.match(request))
  );
});