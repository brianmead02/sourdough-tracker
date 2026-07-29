// IndexedDB-backed outbox for writes made while offline.
//
// A baker's kitchen has bad wifi and a phone in a pocket. Losing a feeding
// because the network blinked is the kind of thing that makes a tracker
// untrustworthy, so mutations are recorded locally and replayed in order.

const DB_NAME = 'sourdough';
const DB_VERSION = 1;
const STORE = 'outbox';

let dbPromise = null;

function open() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return dbPromise;
}

function transact(mode, work) {
  return open().then(
    (db) =>
      new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const store = tx.objectStore(STORE);
        const result = work(store);
        tx.oncomplete = () => resolve(result?.result ?? result);
        tx.onerror = () => reject(tx.error);
      }),
  );
}

export async function queueWrite(entry) {
  return transact('readwrite', (store) => store.add({ ...entry, queued_at: Date.now() }));
}

export async function pendingCount() {
  return transact('readonly', (store) => store.count());
}

export async function pendingWrites() {
  return transact('readonly', (store) => store.getAll());
}

export async function clearQueue() {
  return transact('readwrite', (store) => store.clear());
}

/**
 * Replay queued writes oldest-first.
 *
 * Order matters: a feeding followed by an observation referencing it must go in
 * that sequence. A permanently-rejected entry (4xx that is not auth) is dropped
 * rather than retried forever — it will never succeed, and a stuck queue blocks
 * everything behind it.
 */
export async function drainQueue(send) {
  const entries = (await pendingWrites()).sort((a, b) => a.queued_at - b.queued_at);
  let sent = 0;
  let dropped = 0;

  for (const entry of entries) {
    try {
      await send(entry);
      sent += 1;
    } catch (error) {
      const status = error?.status ?? 0;
      if (status === 0 || status >= 500 || status === 401) {
        // Still offline, server trouble, or needs a fresh login: stop and keep
        // the rest of the queue intact for the next attempt.
        break;
      }
      dropped += 1;
    }
    await transact('readwrite', (store) => store.delete(entry.id));
  }

  return { sent, dropped, remaining: await pendingCount() };
}
