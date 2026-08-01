/**
 * Browser-side logic tests. Run with:  node web/test/app.test.mjs
 *
 * These cover the two places where a bug costs the user something real: the
 * countdown (wrong by an hour and the loaf over-proofs) and the offline outbox
 * (wrong and a feeding is silently lost). Browser globals are stubbed rather
 * than mocked out of the code, so the modules under test are the ones shipped.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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

const attributes = new Map();
globalThis.document = {
  documentElement: {
    setAttribute: (k, v) => attributes.set(k, v),
    removeAttribute: (k) => attributes.delete(k),
    getAttribute: (k) => attributes.get(k) ?? null,
  },
};

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

const { app, applyTheme, NAVIGABLE, PRIMARY, parseAmount, ROUTES, SECONDARY, TITLES } =
  await import('../js/app.js');
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

// --- navigation coverage ---------------------------------------------------
//
// Nine routes existed, the nav had six buttons, and nothing linked the other
// three: inventory, achievements and leaderboard shipped reachable only by
// typing the hash. These tests exist so that cannot recur silently.

test('every route is reachable from the navigation', () => {
  const missing = ROUTES.filter((route) => !NAVIGABLE.includes(route));
  assert.deepEqual(
    missing, [],
    `unreachable route(s): ${missing.join(', ')} — add each to PRIMARY or SECONDARY in app.js`,
  );
});

test('the navigation offers nothing that is not a route', () => {
  const bogus = NAVIGABLE.filter((route) => !ROUTES.includes(route));
  assert.deepEqual(bogus, [], `navigation points at non-route(s): ${bogus.join(', ')}`);
});

test('no destination appears in both the tab bar and the sheet', () => {
  const overlap = PRIMARY.filter((d) => SECONDARY.some((s) => s.route === d.route));
  assert.deepEqual(overlap.map((d) => d.route), []);
});

test('the tab bar holds five destinations, leaving the sixth slot for More', () => {
  assert.equal(PRIMARY.length, 5);
});

test('every destination has a title, and sheet entries explain themselves', () => {
  for (const d of [...PRIMARY, ...SECONDARY]) {
    assert.ok(TITLES[d.route], `${d.route} has no title`);
    assert.ok(d.icon, `${d.route} has no icon`);
  }
  for (const d of SECONDARY) {
    assert.ok(d.hint && d.hint.length > 8, `${d.route} needs a hint for the More sheet`);
  }
});

test('opening a destination closes the More sheet', () => {
  const a = app();
  a.moreOpen = true;
  a.go('inventory', false);
  assert.equal(a.view, 'inventory');
  assert.equal(a.moreOpen, false);
});

// --- theme ----------------------------------------------------------------

test('theme cycles auto to light to dark and back, and persists', () => {
  const a = app();
  assert.equal(a.theme, 'auto', 'defaults to following the device');

  a.cycleTheme();
  assert.equal(a.theme, 'light');
  assert.equal(document.documentElement.getAttribute('data-theme'), 'light');
  assert.equal(localStorage.getItem('sd-theme'), 'light');

  a.cycleTheme();
  assert.equal(a.theme, 'dark');
  assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');

  a.cycleTheme();
  assert.equal(a.theme, 'auto');
  assert.equal(document.documentElement.getAttribute('data-theme'), null,
    'auto must remove the attribute so prefers-color-scheme takes over again');
});

test('a stored theme is restored on the next visit', () => {
  localStorage.setItem('sd-theme', 'dark');
  assert.equal(app().theme, 'dark');
  localStorage.setItem('sd-theme', 'not-a-theme');
  assert.equal(app().theme, 'auto', 'a junk value must not break startup');
  localStorage.removeItem('sd-theme');
});

test('applyTheme is idempotent and reversible', () => {
  applyTheme('dark');
  applyTheme('dark');
  assert.equal(document.documentElement.getAttribute('data-theme'), 'dark');
  applyTheme('auto');
  assert.equal(document.documentElement.getAttribute('data-theme'), null);
});

// --- amount parsing --------------------------------------------------------
//
// The one place a baker's typing becomes a stored quantity. A misread unit does
// not show a wrong number, it saves one.

test('a bare number is grams, matching the field it replaces', () => {
  assert.deepEqual(parseAmount('10000'), { quantity_g: 10000 });
  assert.deepEqual(parseAmount('12 g'), { quantity_g: 12 });
  assert.deepEqual(parseAmount('  250  '), { quantity_g: 250 });
});

test('units are recognised however they are spelled', () => {
  assert.deepEqual(parseAmount('5 lb'), { quantity: 5, unit: 'lb' });
  assert.deepEqual(parseAmount('5 pounds'), { quantity: 5, unit: 'lb' });
  assert.deepEqual(parseAmount('10 cups'), { quantity: 10, unit: 'cup' });
  assert.deepEqual(parseAmount('2 Tablespoons'), { quantity: 2, unit: 'tbsp' });
  assert.deepEqual(parseAmount('1.5 kg'), { quantity: 1.5, unit: 'kg' });
  assert.deepEqual(parseAmount('3 fl oz'), { quantity: 3, unit: 'fl_oz' });
});

test('anything unreadable returns null rather than a guess', () => {
  for (const bad of ['', '   ', 'abc', '7 furlongs', '-5 lb', '0 cup', 'lb', '1 2 cup']) {
    assert.equal(parseAmount(bad), null, JSON.stringify(bad));
  }
});

test('parseAmount never invents a unit the API does not have', () => {
  const KNOWN = new Set(['kg', 'oz', 'lb', 'ml', 'l', 'cup', 'tbsp', 'tsp', 'fl_oz', 'pint', 'quart']);
  for (const text of ['5 lb', '10 cups', '2 tsp', '1 quart', '3 pints', '4 litres']) {
    const parsed = parseAmount(text);
    if (parsed && parsed.unit) assert.ok(KNOWN.has(parsed.unit), `${text} -> ${parsed.unit}`);
  }
});

// --- markup guards ---------------------------------------------------------

const MARKUP = readFileSync(new URL('../index.html', import.meta.url), 'utf8');

test('every <img> declares alt, width, height and loading', () => {
  // Missing width/height is layout shift: the card jumps when the image lands.
  // Missing alt is a screen reader reading out a filename. Neither shows up in
  // a screenshot, so they are asserted rather than eyeballed.
  const tags = MARKUP.match(/<img[\s\S]*?>/g) ?? [];
  assert.ok(tags.length > 0, 'expected at least one <img>');
  for (const tag of tags) {
    for (const attr of ['alt', 'width', 'height', 'loading']) {
      assert.ok(tag.includes(`${attr}=`), `${attr} missing from ${tag}`);
    }
  }
});

test('no image is precached in the service worker shell', () => {
  // The shell is what a cold visitor downloads before the app renders. A
  // sign-in illustration is not part of that, and the budget check only stays
  // meaningful while this holds.
  const sw = readFileSync(new URL('../sw.js', import.meta.url), 'utf8');
  const shell = sw.match(/const SHELL = \[(.*?)\];/s)?.[1] ?? '';
  const images = [...shell.matchAll(/'([^']+\.(?:webp|png|jpe?g|avif))'/g)].map((m) => m[1]);
  assert.deepEqual(images, [], `images in SHELL: ${images.join(', ')}`);
});

test('every <use> in the markup points at a symbol that exists', () => {
  const symbols = new Set([...MARKUP.matchAll(/<symbol id="([^"]+)"/g)].map((m) => m[1]));
  const refs = [...MARKUP.matchAll(/<use href="#([^"]+)"/g)].map((m) => m[1]);
  const missing = refs.filter((r) => !symbols.has(r));
  assert.deepEqual(missing, [], `unresolved icon reference(s): ${missing.join(', ')}`);
});
