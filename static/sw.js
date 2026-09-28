const CACHE_NAME = 'aulapdf-v2';
const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/images/logo_aula_pdf.png',
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js',
  'https://cdn.jsdelivr.net/npm/page-flip/dist/js/page-flip.browser.min.js'
];

self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // For HTML navigation or dynamic routes, ALWAYS use Network First
  if (event.request.mode === 'navigate' || event.request.destination === 'document' || url.pathname.startsWith('/admin') || url.pathname.startsWith('/pdf')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          return response;
        })
        .catch(() => {
          return caches.match(event.request);
        })
    );
    return;
  }

  // For static assets, try Cache First then Network
  event.respondWith(
    caches.match(event.request).then(cached => {
      return cached || fetch(event.request).then(response => {
        return response;
      });
    })
  );
});
