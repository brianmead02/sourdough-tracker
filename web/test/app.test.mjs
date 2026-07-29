/**
 * Browser-side logic tests. Run with:  node web/test/app.test.mjs
 *
 * These cover the two places where a bug costs the user something real: the
 * countdown (wrong by an hour and the loaf over-proofs) and the offline outbox
 * (wrong and a feeding is silently lost). Browser globals are stubbed rather
 * than mocked out of the code, so the modules under test are the ones shipped.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

// --- browser stubs ---------------------------------------------------------

const storage = new Map();
globalThis.localStorage = {
  getItem: (k) => storage.get(k) ?? null,
  setItem: (k, v) => storage.set(k, v),
  removeItem: (k) => storage.delete(k),
};
Object.defineProperty(globalThis, 'navigator', {
  configurable: true,
  value: { onLine: true, platform: 'test' },
});
globalThis.window = { addEventListener() {} };
globalThis.location = { hash: '#/dashboard', search: '' };
globalThis.setInterval = () => 0;

let nextId = 0;
let rows = new Map();
const request = (result) => {
  const r = { result };
  queueMicrotask(() => r.onsuccess && r.onsuccess());
  return r;
};
const objectStore = {
  add: (v) => { const id = ++nextId; rows.set(id, { ...v, id }); return request(id); },
  getAll: () => request([...rows.values()]),
  count: () => request(rows.size),
  delete: (id) => { rows.delete(id); return request(undefined); },
  clear: () => { rows.clear(); return request(undefined); },
};
Object.defineProperty(globalThis, 'indexedDB', {
  configurable: true,
  value: {
    open() {
      const r = {};
      queueMicrotask(() => {
        r.result = {
          objectStoreNames: { contains: () => true },
          createObjectStore() {},
          transaction: () => ({
            objectStore: () => objectStore,
            set oncomplete(fn) { queueMicrotask(fn); },
            set onerror(_) {},
          }),
        };
        r.onsuccess && r.onsuccess();
      });
      return r;
    },
  },
});

const { app } = await import('../js/app.js');
const { queueWrite, drainQueue, pendingCount, clearQueue } = await import('../js/db.js');

const reset = async () => { await clearQueue(); nextId = 0; };

// --- countdown -------------------------------------------------------------

test('countdown formats hours and minutes', () => {
  const a = app();
  a.now = Date.parse('2026-07-29T12:00:00Z');
  assert.equal(a.countdown('2026-07-29T14:01:00Z'), '2h 01m');
});

test('countdown switches to minutes and seconds under an hour', () => {
  const a = app();
  a.now = Date.parse('2026-07-29T12:00:00Z');
  assert.equal(a.countdown('2026-07-29T12:02:05Z'), '2:05');
});

test('countdown reads "ready" at and past the deadline', () => {
  const a = app();
  a.now = Date.parse('2026-07-29T12:00:00Z');
  assert.equal(a.countdown('2026-07-29T12:00:00Z'), 'ready');
  assert.equal(a.countdown('2026-07-29T11:00:00Z'), 'ready');
  assert.equal(a.isReady('2026-07-29T11:00:00Z'), true);
  assert.equal(a.isReady('2026-07-29T13:00:00Z'), false);
});

// --- formatting ------------------------------------------------------------

test('money renders two decimals and tolerates nothing', () => {
  const a = app();
  assert.equal(a.money(1.5), '1.50');
  assert.equal(a.money(0), '0.00');
  assert.equal(a.money(null), '—');
});

test('relative time survives a null timestamp', () => {
  assert.equal(app().relative(null), 'never');
});

// --- routing ---------------------------------------------------------------

test('routing accepts known views and falls back for anything else', () => {
  const a = app();
  a.go('leaderboard', false);
  assert.equal(a.view, 'leaderboard');
  a.go('../../etc/passwd', false);
  assert.equal(a.view, 'dashboard');
});

// --- offline outbox --------------------------------------------------------

test('queued writes replay oldest-first', async () => {
  await reset();
  await queueWrite({ path: '/starters/1/feedings', method: 'POST' });
  await queueWrite({ path: '/starters/1/observations', method: 'POST' });
  assert.equal(await pendingCount(), 2);

  const seen = [];
  const result = await drainQueue(async (entry) => { seen.push(entry.path); });

  assert.equal(result.sent, 2);
  assert.equal(await pendingCount(), 0);
  assert.deepEqual(seen, ['/starters/1/feedings', '/starters/1/observations']);
});

test('a permanently rejected write is dropped, not retried forever', async () => {
  await reset();
  await queueWrite({ path: '/bad', method: 'POST' });
  await queueWrite({ path: '/good', method: 'POST' });

  const attempted = [];
  const result = await drainQueue(async (entry) => {
    attempted.push(entry.path);
    if (entry.path === '/bad') {
      const error = new Error('unprocessable');
      error.status = 422;
      throw error;
    }
  });

  assert.equal(result.dropped, 1);
  assert.equal(result.sent, 1);
  assert.ok(attempted.includes('/good'), 'a bad entry must not block the queue');
  assert.equal(await pendingCount(), 0);
});

for (const [label, status] of [['offline', 0], ['server error', 503], ['expired session', 401]]) {
  test(`the queue survives a ${label}`, async () => {
    await reset();
    await queueWrite({ path: '/a', method: 'POST' });
    await queueWrite({ path: '/b', method: 'POST' });

    const result = await drainQueue(async () => {
      const error = new Error(label);
      error.status = status;
      throw error;
    });

    assert.equal(result.sent, 0);
    assert.equal(await pendingCount(), 2, 'nothing may be lost');
  });
}
