// Service worker: offline shell, Web Push receiver, and background sync.
//
// Caching policy is deliberately split:
//   * the app shell is cache-first  — it changes only on deploy
//   * the API is network-first      — a stale streak or ETA is worse than a
//                                     spinner, and proofing data ages in minutes
//
// The version string is what invalidates the shell. Bump it on deploy.

const VERSION = 'v4';
const SHELL_CACHE = `sourdough-shell-${VERSION}`;
const DATA_CACHE = `sourdough-data-${VERSION}`;

const SHELL = [
  '/',
  '/index.html',
  '/css/app.css',
  '/js/app.js',
  '/js/api.js',
  '/js/db.js',
  '/vendor/alpine-3.14.8.min.js',
  '/vendor/inter-4.1-latin.woff2',
  '/manifest.json',
  '/icons/icon.svg',
];

// Read-only endpoints worth keeping a copy of, so opening the app underground
// still shows yesterday's starters rather than an error page.
const CACHEABLE_API = [
  '/api/v1/starters',
  '/api/v1/starters/schedule',
  '/api/v1/proofing/sessions/active',
  '/api/v1/gamification/tier',
  '/api/v1/recipes',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== SHELL_CACHE && key !== DATA_CACHE)
          .map((key) => caches.delete(key)),
      ))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return; // writes are the outbox's job, not ours

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request, url));
    return;
  }
  event.respondWith(cacheFirst(request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(SHELL_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // A navigation that misses the cache still gets the shell: hash routing
    // means every screen lives in index.html.
    if (request.mode === 'navigate') {
      const shell = await caches.match('/index.html');
      if (shell) return shell;
    }
    throw new Error('offline and not cached');
  }
}

async function networkFirst(request, url) {
  const cacheable = CACHEABLE_API.some((path) => url.pathname === path);
  try {
    const response = await fetch(request);
    if (response.ok && cacheable) {
      const cache = await caches.open(DATA_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = cacheable ? await caches.match(request) : null;
    if (cached) return cached;
    return new Response(JSON.stringify({ detail: 'Offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

// --- Web Push --------------------------------------------------------------

self.addEventListener('push', (event) => {
  let payload = { title: 'Sourdough Tracker', body: 'You have a new reminder.' };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch {
    if (event.data) payload.body = event.data.text();
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      // Reminders about the same thing should replace, not stack: three
      // "dough is ready" notifications are worse than one.
      tag: payload.event || 'sourdough',
      renotify: true,
      data: payload.data || {},
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = event.notification.data?.session_id ? '/#/proofing' : '/#/dashboard';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});

// --- background sync -------------------------------------------------------

self.addEventListener('sync', (event) => {
  if (event.tag === 'sourdough-outbox') {
    // The page owns the outbox (it has the auth tokens); waking a client is
    // enough to make it drain.
    event.waitUntil(
      self.clients.matchAll({ includeUncontrolled: true }).then((clients) => {
        clients.forEach((client) => client.postMessage({ type: 'drain-outbox' }));
      }),
    );
  }
});
