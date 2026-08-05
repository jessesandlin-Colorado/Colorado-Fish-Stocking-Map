const VERSION = 'cofish-pwa-v3';
const SHELL_CACHE = `${VERSION}-shell`;
const RUNTIME_CACHE = `${VERSION}-runtime`;
const BASE = new URL('./', self.location.href);
const shell = [
  './', './index.html', './offline.html', './styles.css', './app.js',
  './mobile-layout.js', './mobile-layout.css', './app-install.js',
  './app-install.css', './cofish-logo.svg', './android-chrome-192x192.png',
  './android-chrome-512x512.png', './site.webmanifest'
].map(path => new URL(path, BASE).href);

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(shell)));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => ![SHELL_CACHE, RUNTIME_CACHE].includes(key)).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

async function networkFirst(request, fallback) {
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (error) {
    return (await cache.match(request)) || (await caches.match(fallback));
  }
}

async function staleWhileRevalidate(request) {
  const cached = await caches.match(request);
  const update = fetch(request).then(response => {
    if (response.ok) caches.open(RUNTIME_CACHE).then(cache => cache.put(request, response.clone()));
    return response;
  }).catch(() => null);
  return cached || update || Response.error();
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, new URL('./offline.html', BASE).href));
    return;
  }
  if (url.pathname.includes('/data/') || url.pathname.includes('/config/')) {
    event.respondWith(networkFirst(request));
    return;
  }
  event.respondWith(staleWhileRevalidate(request));
});

self.addEventListener('message', event => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});
