const STATIC_CACHE = 'ur-hud-static-v2';
const DYNAMIC_CACHE = 'ur-hud-dynamic-v2';
const API_CACHE = 'ur-hud-api-v2';
const OFFLINE_DOC_CACHE = 'ur-hud-offline-documents';
const OFFLINE_URLS = ['/', '/index.html', '/manifest.webmanifest'];

function isApiRequest(request) {
  return request.url.includes('/api/');
}

function isDocumentAsset(request) {
  return /\.(pdf|png|jpg|jpeg|webp|gif|svg)$/i.test(request.url);
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(OFFLINE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) =>
      Promise.all(
        cacheNames
          .filter((cacheName) => ![STATIC_CACHE, DYNAMIC_CACHE, API_CACHE, OFFLINE_DOC_CACHE].includes(cacheName))
          .map((cacheName) => caches.delete(cacheName))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    return;
  }

  if (event.request.url.includes('/offline-docs/')) {
    event.respondWith(
      caches.open(OFFLINE_DOC_CACHE).then(async (cache) => {
        const cached = await cache.match(event.request);
        if (cached) {
          return cached;
        }
        return caches.match(event.request).then((fallback) => fallback || caches.match('/index.html'));
      })
    );
    return;
  }

  if (isApiRequest(event.request)) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const responseToCache = response.clone();
          caches.open(API_CACHE).then((cache) => cache.put(event.request, responseToCache));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  if (isDocumentAsset(event.request)) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request)
          .then((response) => {
            const responseToCache = response.clone();
            caches.open(DYNAMIC_CACHE).then((cache) => cache.put(event.request, responseToCache));
            return response;
          })
          .catch(() => caches.match('/index.html'));
      })
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request)
        .then((response) => {
          if (!response || response.status !== 200 || response.type !== 'basic') {
            return response;
          }
          const responseToCache = response.clone();
          caches.open(DYNAMIC_CACHE).then((cache) => cache.put(event.request, responseToCache));
          return response;
        })
        .catch(() => caches.match('/index.html'));
    })
  );
});
