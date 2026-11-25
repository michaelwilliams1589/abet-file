// OSUIT ABET File service worker. Bump VERSION on every release (also bump ?v=N on assets).
const VERSION = 'v1';
const CACHE = 'abet-shell-' + VERSION;
const SHELL = [
  './',
  'index.html',
  'meetings.html',
  'assessment.html',
  'self-study.html',
  'log.html',
  'previous.html',
  '404.html',
  'common.css?v=1',
  'common.js?v=1',
  'data.js?v=1',
  'manifest.json?v=1',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/icon-maskable-512.png',
  'icons/apple-touch-icon.png?v=1',
  'icons/favicon-32.png?v=1',
  'icons/favicon.ico?v=1'
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => Promise.allSettled(SHELL.map(u => c.add(new Request(u, { cache: 'reload' })))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('abet-shell-') && k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Only handle our origin. Google Drive (and any other cross-origin) requests go to the network, never cached.
  if (url.origin !== self.location.origin) return;
  if (url.pathname.endsWith('/sw.js')) return;

  const isPage = req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html');
  if (isPage) {
    e.respondWith(
      fetch(req).then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
        return res;
      }).catch(() => caches.match(req, { ignoreSearch: true }).then(r => r || caches.match('index.html')))
    );
    return;
  }
  e.respondWith(
    caches.open(CACHE).then(c => c.match(req).then(hit => {
      const net = fetch(req).then(res => { if (res.ok) c.put(req, res.clone()); return res; }).catch(() => hit);
      return hit || net;
    }))
  );
});
