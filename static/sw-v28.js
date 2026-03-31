const CACHE_NAME = 'trippool-cache-v26';
const STATIC_ASSETS = [
  '/login',
  '/static/css/index.css',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  const path = url.pathname;

  // NEVER cache API routes - always go to network
  if (path.startsWith('/api/') || path === '/register' || path === '/login' || path === '/logout') {
    event.respondWith(fetch(event.request));
    return;
  }

  // Network-First for all navigation pages
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .catch(() => caches.match('/login'))
    );
    return;
  }

  // Cache-First for static assets only
  if (path.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(response => {
        return response || fetch(event.request);
      })
    );
    return;
  }

  // Default: Network-Only
  event.respondWith(fetch(event.request));
});
