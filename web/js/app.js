// The Alpine component behind the whole app.
//
// Routing is hash-based (#/starters) on purpose: it needs no server rewrite
// rule, which keeps the PWA servable by anything — Caddy, the API's own static
// mount, or a plain file server — and makes offline navigation trivial.

import { api, ApiError, clearSession, flushQueue, isAuthenticated, login, logout, register, verifyEmail } from './api.js';
import { pendingCount } from './db.js';

export const ROUTES = ['dashboard', 'starters', 'proofing', 'bakes', 'recipes', 'inventory',
  'achievements', 'leaderboard', 'settings'];

// Navigation is data, not markup. It used to be six hand-written buttons, and
// because ROUTES has nine entries, inventory, achievements and leaderboard were
// reachable only by typing the hash. A test asserts these two lists cover ROUTES.
export const PRIMARY = [
  { route: 'dashboard', label: 'Today', icon: 'home' },
  { route: 'starters', label: 'Starters', icon: 'jar' },
  { route: 'proofing', label: 'Proof', icon: 'timer' },
  { route: 'bakes', label: 'Bakes', icon: 'bread' },
  { route: 'recipes', label: 'Recipes', icon: 'book' },
];

export const SECONDARY = [
  { route: 'inventory', label: 'Inventory', icon: 'box', hint: 'Flour, stock and per-loaf cost' },
  { route: 'achievements', label: 'Badges', icon: 'medal', hint: 'Which ones you have earned' },
  { route: 'leaderboard', label: 'Ranking', icon: 'chart', hint: 'Where you stand this season' },
  { route: 'settings', label: 'Settings', icon: 'sliders', hint: 'Reminders, quiet hours, devices' },
];

export const NAVIGABLE = [...PRIMARY, ...SECONDARY].map((d) => d.route);

export const TITLES = Object.fromEntries(
  [...PRIMARY, ...SECONDARY].map((d) => [d.route, d.label]),
);
TITLES.dashboard = 'Today';

// Labels, not capitalised keys: text-transform turned 'xp' into 'Xp'.
export const BOARD_CATEGORIES = [
  { key: 'xp', label: 'Season XP' },
  { key: 'lifetime', label: 'Lifetime XP' },
  { key: 'bakes', label: 'Bakes' },
  { key: 'streak', label: 'Streak' },
  { key: 'crumb', label: 'Crumb' },
  { key: 'achievements', label: 'Badges' },
];

const THEMES = ['auto', 'light', 'dark'];

/**
 * Parse "5 lb", "10 cup", "2000" into a transaction body.
 *
 * Exported and pure so it can be tested: this is the one place in the client
 * where a baker's typing becomes a quantity, and getting the unit wrong stores a
 * wrong number rather than showing one. A bare number means grams, matching the
 * field it replaces.
 *
 * Returns null for anything unparseable — the caller must not guess.
 */
export function parseAmount(text) {
  const match = String(text ?? '').trim().match(/^([\d.]+)\s*([a-zA-Z_ ]*)$/);
  const amount = Number(match?.[1]);
  if (!match || !Number.isFinite(amount) || amount <= 0) return null;

  const unit = (match[2] ?? '').trim().toLowerCase()
    .replace(/\s+/g, '_')
    .replace(/e?s$/, '');            // cups -> cup, ounces -> ounce
  const ALIASES = {
    '': 'g', g: 'g', gram: 'g', kg: 'kg', kilogram: 'kg',
    oz: 'oz', ounce: 'oz', lb: 'lb', pound: 'lb',
    ml: 'ml', l: 'l', litre: 'l', liter: 'l',
    cup: 'cup', tbsp: 'tbsp', tablespoon: 'tbsp', tsp: 'tsp', teaspoon: 'tsp',
    fl_oz: 'fl_oz', pint: 'pint', quart: 'quart',
  };
  const resolved = ALIASES[unit];
  if (!resolved) return null;
  return resolved === 'g'
    ? { quantity_g: amount }
    : { quantity: amount, unit: resolved };
}

function currentRoute() {
  const hash = location.hash.replace(/^#\/?/, '').split('?')[0];
  return ROUTES.includes(hash) ? hash : 'dashboard';
}

function storedTheme() {
  try {
    const value = localStorage.getItem('sd-theme');
    return THEMES.includes(value) ? value : 'auto';
  } catch {
    return 'auto';
  }
}

// 'auto' means "remove the attribute and let prefers-color-scheme decide". The
// explicit values have to win in both directions, which is why the stylesheet
// defines data-theme="light" as well as dark.
export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === 'auto') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme);
}

export function app() {
  return {
    // --- state ---------------------------------------------------------
    ready: false,
    authed: false,
    view: currentRoute(),
    authMode: 'login',
    busy: false,
    toast: null,
    online: navigator.onLine,
    pending: 0,
    now: Date.now(),

    me: null,
    tier: null,
    unread: 0,

    forms: {
      login: { email: '', password: '' },
      register: { email: '', password: '', handle: '', display_name: '', timezone: guessZone() },
      verify: { token: '' },
      starter: { name: '', flour_type: 'bread', ratio_starter: 1, ratio_flour: 5, ratio_water: 5, feed_interval_hours: 24 },
      proof: { stage: 'bulk', dough_temp_c: 24, starter_pct: 20, starter_id: '' },
      check: {},
      bake: { title: '', total_flour_g: 1000, hydration_pct: 70, loaf_count: 1 },
      item: { name: '', kind: 'flour', low_threshold_g: 1000 },
      purchase: {},
      rating: {},
    },

    starters: [],
    schedule: [],
    proofs: [],
    proofHistory: [],
    bakes: [],
    recipes: [],
    publicRecipes: [],
    scaled: null,
    items: [],
    achievements: [],
    board: { rows: [], season_name: '', category: 'xp' },
    myRank: null,
    inbox: { items: [], unread_count: 0 },
    notifSettings: null,
    channels: [],
    showNew: null,
    moreOpen: false,
    theme: storedTheme(),
    // 'metric' | 'us'. Mirrors user_profile.units and is sent as ?units= on the
    // read paths that quote quantities, so the server does the rendering and the
    // two clients cannot disagree about what "3¾ cups" means.
    units: 'metric',

    // exposed so the markup iterates data instead of repeating buttons
    PRIMARY,
    SECONDARY,
    TITLES,
    BOARD_CATEGORIES,

    // --- lifecycle -----------------------------------------------------
    async init() {
      applyTheme(this.theme);
      this.authed = isAuthenticated();
      window.addEventListener('hashchange', () => this.go(currentRoute(), false));
      window.addEventListener('online', () => this.onNetwork(true));
      window.addEventListener('offline', () => this.onNetwork(false));
      // A live countdown is the point of the proofing screen.
      setInterval(() => { this.now = Date.now(); }, 1000);

      const token = new URLSearchParams(location.search).get('token');
      if (token && location.pathname.includes('verify')) this.forms.verify.token = token;

      if (this.authed) await this.bootstrap();
      this.pending = await pendingCount().catch(() => 0);
      this.ready = true;
    },

    async bootstrap() {
      try {
        this.me = await api.get('/auth/me');
        this.units = this.me?.profile?.units ?? 'metric';
        await Promise.all([this.loadTier(), this.loadInbox()]);
        await this.load(this.view);
      } catch (error) {
        if (error.status === 401) this.signOut();
        else this.fail(error);
      }
    },

    async onNetwork(online) {
      this.online = online;
      if (!online) return;
      const result = await flushQueue().catch(() => null);
      this.pending = await pendingCount().catch(() => 0);
      if (result?.sent) {
        this.say(`Synced ${result.sent} offline change${result.sent === 1 ? '' : 's'}`);
        await this.load(this.view);
      }
      if (result?.dropped) this.say(`${result.dropped} offline change(s) were rejected`, true);
    },

    // --- helpers -------------------------------------------------------
    say(message, isError = false) {
      this.toast = { message, isError };
      setTimeout(() => { this.toast = null; }, isError ? 5200 : 2600);
    },

    fail(error) {
      this.say(error instanceof ApiError ? error.message : String(error), true);
    },

    async guard(work, successMessage) {
      this.busy = true;
      try {
        const result = await work();
        if (result?.queued) this.say('Saved offline — will sync when you reconnect');
        else if (successMessage) this.say(successMessage);
        this.pending = await pendingCount().catch(() => 0);
        return result;
      } catch (error) {
        this.fail(error);
        return null;
      } finally {
        this.busy = false;
      }
    },

    go(view, updateHash = true) {
      this.view = ROUTES.includes(view) ? view : 'dashboard';
      this.showNew = null;
      this.moreOpen = false;
      if (updateHash) location.hash = `#/${this.view}`;
      if (this.authed) this.load(this.view);
    },

    title() { return TITLES[this.view] ?? 'Today'; },

    async setUnits(units) {
      const previous = this.units;
      this.units = units;
      const saved = await this.guard(() => api.patch('/profiles/me', { units }));
      if (!saved) {
        this.units = previous;
        return;
      }
      if (this.me?.profile) this.me.profile.units = units;
      this.say(units === 'us' ? 'Showing cups and ounces' : 'Showing grams');
      await this.load(this.view);
    },

    /** The measurement, with its caveat, or null when there is nothing to add. */
    measure(display) {
      if (!display) return null;
      const suffix = display.advise_weighing ? ' · weigh if you can' : '';
      return display.text + suffix;
    },

    /** True when a rendering is a ±20% guess rather than a matched density. */
    isGuess(display) {
      return Boolean(display) && display.basis === 'kind_default';
    },

    cycleTheme() {
      this.theme = THEMES[(THEMES.indexOf(this.theme) + 1) % THEMES.length];
      applyTheme(this.theme);
      try { localStorage.setItem('sd-theme', this.theme); } catch { /* private mode */ }
    },

    themeIcon() {
      return this.theme === 'light' ? 'sun' : this.theme === 'dark' ? 'moon' : 'auto';
    },

    // --- data loading --------------------------------------------------
    async load(view) {
      try {
        if (view === 'dashboard') {
          [this.schedule, this.proofs] = await Promise.all([
            api.get('/starters/schedule'),
            api.get('/proofing/sessions/active'),
          ]);
          await this.loadTier();
        } else if (view === 'starters') {
          this.starters = await api.get('/starters');
        } else if (view === 'proofing') {
          [this.proofs, this.proofHistory, this.starters] = await Promise.all([
            api.get('/proofing/sessions/active'),
            api.get('/proofing/sessions?status=done&limit=10'),
            api.get('/starters'),
          ]);
        } else if (view === 'bakes') {
          [this.bakes, this.recipes] = await Promise.all([
            api.get('/bakes?limit=30'),
            api.get('/recipes'),
          ]);
        } else if (view === 'recipes') {
          [this.recipes, this.publicRecipes] = await Promise.all([
            api.get('/recipes'),
            api.get('/recipes/public?sort=stars&limit=20'),
          ]);
        } else if (view === 'inventory') {
          this.items = await api.get(`/inventory/items?units=${this.units}`);
        } else if (view === 'achievements') {
          this.achievements = await api.get('/gamification/achievements');
          await this.loadTier();
        } else if (view === 'leaderboard') {
          await this.loadBoard(this.board.category);
        } else if (view === 'settings') {
          [this.notifSettings, this.channels] = await Promise.all([
            api.get('/notifications/settings'),
            api.get('/notifications/channels'),
          ]);
          await this.loadInbox();
        }
      } catch (error) {
        if (error.status === 401) this.signOut();
        else if (this.online) this.fail(error);
      }
    },

    async loadTier() { this.tier = await api.get('/gamification/tier').catch(() => null); },
    async loadInbox() {
      this.inbox = await api.get('/notifications/inbox?limit=20').catch(() => this.inbox);
      this.unread = this.inbox.unread_count || 0;
    },
    async loadBoard(category) {
      this.board.category = category;
      const [page, mine] = await Promise.all([
        api.get(`/leaderboard?category=${category}&limit=25`),
        api.get('/leaderboard/me').catch(() => null),
      ]);
      this.board = { ...page, category };
      this.myRank = mine;
    },

    // --- auth ----------------------------------------------------------
    async doLogin() {
      await this.guard(async () => {
        await login(this.forms.login.email, this.forms.login.password);
        this.authed = true;
        await this.bootstrap();
      });
    },

    async doRegister() {
      const result = await this.guard(() => register(this.forms.register));
      if (result) {
        this.authMode = 'verify';
        this.say('Check your email for the confirmation link');
      }
    },

    async doVerify() {
      const result = await this.guard(() => verifyEmail(this.forms.verify.token.trim()),
        'Email confirmed — you can log in now');
      if (result) this.authMode = 'login';
    },

    async signOut() {
      await logout().catch(() => {});
      clearSession();
      this.authed = false;
      this.me = null;
      this.say('Signed out');
    },

    // --- starters ------------------------------------------------------
    async createStarter() {
      const done = await this.guard(() => api.post('/starters', this.forms.starter), 'Starter created');
      if (done) {
        this.forms.starter.name = '';
        this.showNew = null;
        await this.load('starters');
      }
    },

    async feed(starter) {
      const suggestion = await api.post(`/starters/${starter.id}/suggested-feed`, { starter_g: 20 })
        .catch(() => ({ starter_g: 20, flour_g: 100, water_g: 100 }));
      const done = await this.guard(
        () => api.post(`/starters/${starter.id}/feedings`, {
          starter_g: suggestion.starter_g, flour_g: suggestion.flour_g, water_g: suggestion.water_g,
        }),
        `Fed ${starter.name}`,
      );
      if (done) await this.load(this.view);
    },

    async retire(starter) {
      if (!confirm(`Retire ${starter.name}? Its history is kept.`)) return;
      await this.guard(() => api.del(`/starters/${starter.id}`), 'Retired');
      await this.load('starters');
    },

    // --- proofing ------------------------------------------------------
    async startProof() {
      const body = { ...this.forms.proof };
      if (!body.starter_id) delete body.starter_id;
      // The field holds whatever scale the form is showing; send it under the
      // matching name and let the server normalise. Sending 75 as Celsius is
      // exactly the mistake the API refuses, so never guess here.
      if (this.units === 'us') {
        body.dough_temp_f = body.dough_temp_c;
        delete body.dough_temp_c;
      }
      const done = await this.guard(() => api.post('/proofing/sessions', body), 'Proof started');
      if (done) { this.showNew = null; await this.load('proofing'); }
    },

    async checkIn(proof) {
      const raw = prompt(`How much has it risen? (%)  target ${proof.target_rise_pct}%`);
      if (raw === null) return;
      const rise_pct = Number(raw);
      if (Number.isNaN(rise_pct)) return this.say('That is not a number', true);
      await this.guard(() => api.post(`/proofing/sessions/${proof.id}/checks`, { rise_pct }), 'ETA updated');
      await this.load(this.view);
    },

    async finishProof(proof) {
      await this.guard(() => api.post(`/proofing/sessions/${proof.id}/complete`, {}), 'Proof finished');
      await this.load(this.view);
    },

    async abortProof(proof) {
      if (!confirm('Abandon this proof?')) return;
      await this.guard(() => api.post(`/proofing/sessions/${proof.id}/abort`), 'Abandoned');
      await this.load(this.view);
    },

    // --- bakes ---------------------------------------------------------
    async createBake() {
      const body = { ...this.forms.bake };
      if (!body.recipe_id) delete body.recipe_id;
      const done = await this.guard(() => api.post('/bakes', body), 'Bake started');
      if (done) { this.forms.bake.title = ''; this.showNew = null; await this.load('bakes'); }
    },

    async completeBake(bake) {
      const done = await this.guard(() => api.post(`/bakes/${bake.id}/complete`, {}));
      if (done && !done.queued) {
        const awards = done.awards || [];
        this.say(awards.length
          ? `+${done.xp_gained} XP · ${awards.map((a) => `${a.icon} ${a.name}`).join(', ')}`
          : `Bake finished · +${done.xp_gained} XP`);
        await this.loadTier();
      }
      await this.load('bakes');
    },

    async rateBake(bake, overall) {
      await this.guard(() => api.put(`/bakes/${bake.id}/rating`, { overall }), 'Rated');
      await this.load('bakes');
    },

    // --- recipes -------------------------------------------------------
    async scale(recipe, doughWeight) {
      this.scaled = await api
        .get(`/recipes/${recipe.id}/scale?dough_weight_g=${doughWeight}&units=${this.units}`)
        .catch((error) => { this.fail(error); return null; });
      if (this.scaled) this.scaled.name = recipe.name;
    },

    async fork(recipe) {
      await this.guard(() => api.post(`/recipes/${recipe.id}/fork`), `Forked ${recipe.name}`);
      await this.load('recipes');
    },

    async star(recipe) {
      await this.guard(() => api.post(`/recipes/${recipe.id}/star`), 'Starred');
      await this.load('recipes');
    },

    // --- inventory -----------------------------------------------------
    async createItem() {
      const done = await this.guard(() => api.post('/inventory/items', this.forms.item), 'Item added');
      if (done) { this.forms.item.name = ''; this.showNew = null; await this.load('inventory'); }
    },

    async buy(item) {
      // In US mode ask for the unit too, so a baker with a bag marked in pounds
      // does not have to convert before they can record it.
      const metric = this.units === 'metric';
      const prompted = prompt(
        metric
          ? `How many grams of ${item.name}?`
          : `How much ${item.name}? e.g. "5 lb", "10 cup", "2000 g"`,
        metric ? '10000' : '5 lb',
      );
      if (!prompted) return;

      const parsed = parseAmount(prompted);
      if (!parsed) return this.say(`Could not read "${prompted}" as an amount`, true);
      const body = { kind: 'purchase', ...parsed };

      const cost = Number(prompt('Cost per kg?', '2.00'));
      if (Number.isNaN(cost)) return;
      body.unit_cost_per_kg = cost;

      await this.guard(
        () => api.post(`/inventory/items/${item.id}/transactions`, body),
        'Stock added',
      );
      await this.load('inventory');
    },

    // --- notifications -------------------------------------------------
    async saveNotifications() {
      await this.guard(() => api.put('/notifications/settings', {
        quiet_hours_start: this.notifSettings.quiet_hours_start,
        quiet_hours_end: this.notifSettings.quiet_hours_end,
      }), 'Saved');
    },

    async markAllRead() {
      await this.guard(() => api.post('/notifications/inbox/read', { all: true }));
      await this.loadInbox();
    },

    async sendTest() {
      await this.guard(() => api.post('/notifications/test', {}),
        'Queued — it should arrive within a minute');
    },

    async enablePush() {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        return this.say('This browser does not support push notifications', true);
      }
      try {
        const { public_key: key, available } = await api.get('/notifications/vapid-key');
        if (!available) return this.say('Web Push is not configured on this server', true);

        const permission = await Notification.requestPermission();
        if (permission !== 'granted') return this.say('Notification permission denied', true);

        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(key),
        });
        const raw = subscription.toJSON();
        await api.post('/notifications/webpush/subscribe', {
          endpoint: raw.endpoint, keys: raw.keys, label: navigator.platform || 'This device',
        });
        this.say('Push notifications enabled');
        await this.load('settings');
      } catch (error) {
        this.fail(error);
      }
    },

    async removeChannel(channel) {
      await this.guard(() => api.del(`/notifications/channels/${channel.id}`), 'Removed');
      await this.load('settings');
    },

    // --- formatting ----------------------------------------------------
    countdown(iso) {
      const ms = new Date(iso).getTime() - this.now;
      if (ms <= 0) return 'ready';
      const total = Math.floor(ms / 1000);
      const h = Math.floor(total / 3600);
      const m = Math.floor((total % 3600) / 60);
      const s = total % 60;
      return h > 0 ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}:${String(s).padStart(2, '0')}`;
    },

    isReady(iso) { return new Date(iso).getTime() - this.now <= 0; },

    relative(iso) {
      if (!iso) return 'never';
      const diff = (new Date(iso).getTime() - this.now) / 1000;
      const abs = Math.abs(diff);
      const [value, unit] = abs < 3600 ? [abs / 60, 'minute']
        : abs < 86400 ? [abs / 3600, 'hour'] : [abs / 86400, 'day'];
      const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
      return formatter.format(Math.round(diff < 0 ? -value : value), unit);
    },

    date(iso) {
      return iso ? new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '';
    },

    money(value) { return value == null ? '—' : value.toFixed(2); },

    /** Baker's percentage, trimmed. Recipes entered as amounts carry four
     *  decimals so scaling stays exact; nobody wants to read 90.0563%. */
    pct(value) {
      if (value == null) return '';
      return `${Math.round(value * 10) / 10}%`;
    },
  };
}

function guessZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch { return 'UTC'; }
}

// VAPID keys arrive base64url-encoded; PushManager wants raw bytes.
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

window.sourdoughApp = app;
