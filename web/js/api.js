// API client: token storage, transparent refresh, and offline queueing.
//
// Access tokens last 15 minutes and refresh tokens rotate on every use, so the
// client has to hold exactly one refresh in flight — otherwise two concurrent
// 401s would both rotate, and the loser's token would be treated by the server
// as a replayed (i.e. leaked) token and kill the whole session.

import { queueWrite, drainQueue } from './db.js';

const BASE = '/api/v1';
const STORAGE_KEY = 'sourdough.tokens';

let tokens = load();
let refreshInFlight = null;

function load() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || null;
  } catch {
    return null;
  }
}

function save(next) {
  tokens = next;
  if (next) localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  else localStorage.removeItem(STORAGE_KEY);
}

export function isAuthenticated() {
  return Boolean(tokens?.access_token);
}

export function clearSession() {
  save(null);
}

async function rawFetch(path, options = {}, withAuth = true) {
  const headers = { ...(options.headers || {}) };
  if (options.body !== undefined && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  if (withAuth && tokens?.access_token) {
    headers['Authorization'] = `Bearer ${tokens.access_token}`;
  }
  return fetch(BASE + path, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

async function refresh() {
  // Collapse concurrent refreshes: the server revokes the presented token, so a
  // second simultaneous attempt would look exactly like a stolen one.
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const response = await rawFetch(
        '/auth/refresh',
        { method: 'POST', body: { refresh_token: tokens.refresh_token } },
        false,
      );
      if (!response.ok) {
        save(null);
        throw new ApiError('Session expired. Please log in again.', 401);
      }
      save(await response.json());
      return tokens;
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function messageFrom(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: surface the field, not just "invalid".
    return detail
      .map((e) => `${(e.loc || []).slice(1).join('.') || 'field'}: ${e.msg}`)
      .join('\n');
  }
  return `Request failed (${status})`;
}

export async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const mutating = method !== 'GET';

  if (mutating && !navigator.onLine && options.queueable !== false) {
    // Log it now, send it when the network comes back. The alternative is
    // losing a feeding because the kitchen has bad wifi.
    await queueWrite({ path, method, body: options.body });
    return { queued: true };
  }

  let response;
  try {
    response = await rawFetch(path, options);
  } catch (networkError) {
    if (mutating && options.queueable !== false) {
      await queueWrite({ path, method, body: options.body });
      return { queued: true };
    }
    throw new ApiError('Network unavailable', 0);
  }

  if (response.status === 401 && tokens?.refresh_token && !options._retried) {
    await refresh();
    return request(path, { ...options, _retried: true });
  }

  if (response.status === 204) return null;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(messageFrom(payload, response.status), response.status, payload?.detail);
  }
  return payload;
}

export const api = {
  get: (path) => request(path),
  post: (path, body, opts) => request(path, { method: 'POST', body, ...opts }),
  put: (path, body, opts) => request(path, { method: 'PUT', body, ...opts }),
  patch: (path, body, opts) => request(path, { method: 'PATCH', body, ...opts }),
  del: (path, opts) => request(path, { method: 'DELETE', ...opts }),
};

export async function login(email, password) {
  const response = await rawFetch(
    '/auth/login',
    { method: 'POST', body: { email, password } },
    false,
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(messageFrom(payload, response.status), response.status);
  save(payload);
  return payload;
}

export async function register(details) {
  const response = await rawFetch('/auth/register', { method: 'POST', body: details }, false);
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(messageFrom(payload, response.status), response.status);
  return payload;
}

export async function verifyEmail(token) {
  const response = await rawFetch('/auth/verify-email', { method: 'POST', body: { token } }, false);
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(messageFrom(payload, response.status), response.status);
  return payload;
}

export async function logout() {
  if (tokens?.refresh_token) {
    await api.post('/auth/logout', { refresh_token: tokens.refresh_token }).catch(() => {});
  }
  save(null);
}

export async function flushQueue() {
  return drainQueue(async ({ path, method, body }) => {
    await request(path, { method, body, queueable: false });
  });
}
