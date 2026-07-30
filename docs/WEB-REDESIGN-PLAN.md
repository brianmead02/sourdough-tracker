# Web Front-End Redesign Plan

Modernise the PWA's look, typography, visibility and navigation without giving
up what makes it work: a ~104 KB offline-first shell with no build step, no
`node_modules`, and no third-party requests.

**Status: built and verified, 2026-07-29.** All six phases landed. What the
finished work measured, against what this plan predicted:

| | Predicted | Actual |
|---|---|---|
| Font subset | 53 KB | **54,316 bytes**, reproducible via `scripts/build_font.py --check` |
| Precached shell | ~157 KB | **183 KB uncompressed / 93 KB over the wire** — see §7 |
| Contrast pairs passing | all | **30/30 in both themes**, and the two dark definitions verified identical |
| Browser-logic tests | 11 + new | **20** |
| Reachable destinations | 9 | **9**, asserted by test and confirmed in a real browser |

---

## 1. Decisions locked in

| Question | Decision |
|---|---|
| Font | **Self-hosted Inter variable**, latin subset, vendored and precached |
| Desktop layout | **Persistent left sidebar + wide content**; bottom bar stays on mobile |
| Scope | **CSS rewrite + targeted markup edits** — nav, header, dashboard grid, a11y attributes |
| Visibility bar | **WCAG AA, verified by computation** — no eyeballing |

Non-goals: a build step, a CSS framework, an icon font, a JS animation library,
changing any API call, or touching the Flutter app.

---

## 2. What the audit actually found

Measured against the current [web/css/app.css](../web/css/app.css) and
[web/index.html](../web/index.html), not assumed.

### 2.1 Three of nine views are unreachable

`ROUTES` in [app.js:10-11](../web/js/app.js#L10-L11) declares nine routes. The
nav in [index.html:478-491](../web/index.html#L478-L491) has six buttons, and
nothing else in the app links to the other three. **`inventory`,
`achievements` and `leaderboard` are complete, working views that a user can
only reach by typing `#/inventory` into the address bar.**

This is the single biggest problem here, and it is a navigation problem rather
than a styling one. Inventory and per-loaf costing was an explicit v1 feature;
right now it ships hidden.

### 2.2 Contrast: three real failures, and the rest is fine

I computed every foreground/background pair in both themes. Most of the palette
is already comfortably AA — the warm brown `--muted` passes at 4.88 on `--bg`
and 5.21 on `--surface`. Three pairs do not:

| Theme | Pair | Ratio | Where it shows |
|---|---|---|---|
| **Dark** | `#fff` on `--accent` `#f59e0b` | **2.15** | Every `button.primary` — Feed now, Create, Start a proof |
| Light | `--muted` on `--surface-2` | 4.48 | `.pill` — the default status chip |
| Light | `--accent` on `--accent-soft` | 4.21 | `.pill.accent` — the tier badge in the header |

The dark-mode primary button is the serious one. White on mid-amber is 2.15:1 —
below even the 3.0 large-text floor. Half the app's primary actions are hard to
read for anyone whose OS is set to dark.

Fixes, also computed:

- Dark primary button: white → `--bg` `#16120e` as the label colour = **8.68**.
  Dark text on amber, which is what the colour wants anyway.
- Light `.pill`: `--muted` `#7a6a58` → `#6e5b48` = **5.55** on `surface-2`,
  6.04 on `bg`. Same hue, one step deeper.
- Light `.pill.accent`: introduce `--accent-deep` `#9a4404` for text on
  `--accent-soft` = **5.50**. `--accent` itself stays `#b45309` for buttons and
  fills, where it already passes at 5.02.

### 2.3 Type is too small in five places

`0.65rem` (10.4 px) nav labels, plus `0.68`, `0.70`, `0.72` and `0.74rem`
elsewhere — five declarations below the 12 px floor. The nav labels are the
worst: they are the permanent navigation of the app, rendered at 10 px.

### 2.4 Keyboard navigation is invisible

`input, select, textarea` get a focus outline. **Buttons get none** — no
`:focus`, no `:focus-visible` anywhere in the file. Since the entire app is
driven by buttons, tabbing through it gives no visual feedback at all.

### 2.5 Desktop is a phone column

`main { max-width: 720px }` never changes. At ≥700 px the bottom bar becomes a
sticky top bar and that is the whole desktop story. On a 2560 px monitor the app
is a narrow strip with the dashboard's stat cards stacked vertically.

### 2.6 Smaller things

- **Emoji as icons** (🏠 🫙 ⏳ 🍞 📖 ⚙️) render differently on every platform and
  are not `aria-hidden`, so a screen reader announces "house building Today".
- **No `prefers-reduced-motion`** — the spinner animates regardless.
- **No theme toggle**; dark mode follows the OS only.
- **Inline styles** in the markup (`style="width:100%"`, `style="font-size:1.6rem"`)
  that belong in classes.
- The header title is a 9-branch inline ternary object literal in an `x-text`.

---

## 3. Typography

### 3.1 The font file

Inter v4 variable, subset to latin + the punctuation and symbols the app
actually uses, with `kern`, `liga`, `calt` and `tnum` retained.

**Verified:** `pyftsubset` takes `InterVariable.woff2` from 344 KB to
**53 KB**. That is a real number from a real run, not an estimate.

```bash
pyftsubset InterVariable.woff2 --output-file=web/vendor/inter-4.1-latin.woff2 \
  --flavor=woff2 --layout-features="kern,liga,calt,tnum" --no-hinting \
  --desubroutinize --unicodes="U+0000-00FF,U+2013,U+2014,U+2018,U+2019,U+201C,U+201D,U+2026,U+00B7,U+2022,U+00D7,U+2192,U+2605,U+2606"
```

The command goes in `scripts/build_font.py` so the artefact is reproducible
rather than a mystery binary in the tree. `fonttools` + `brotli` are dev-only —
they never enter the runtime image.

```css
@font-face {
  font-family: 'Inter';
  font-weight: 100 900;          /* one file, whole weight axis */
  font-display: swap;
  src: url('/vendor/inter-4.1-latin.woff2') format('woff2');
}
```

`swap`, not `optional`: the service worker precaches the file, so after the
first visit it is instant, and on that first visit readable fallback text beats
invisible text.

**Cost:** the shell goes from 104 KB to ~157 KB, a 51% increase. That is the
real price of this decision and it is worth stating plainly. It buys identical
rendering everywhere and, more usefully, genuine tabular numerals — the
countdown, leaderboard ranks and stat values all currently rely on
`font-variant-numeric: tabular-nums` being honoured by whatever the OS supplies.

### 3.2 The scale

Replaces 14 ad-hoc `rem` values with seven tokens. **Nothing below 13 px.**

| Token | Size | Used for |
|---|---|---|
| `--fs-xs` | 0.8125rem / 13px | pills, badge captions, meta — the floor |
| `--fs-sm` | 0.875rem / 14px | labels, `.sub`, small buttons, nav labels |
| `--fs-base` | 1rem / 16px | body, inputs, buttons |
| `--fs-lg` | 1.125rem / 18px | card headings |
| `--fs-xl` | 1.375rem / 22px | view titles, stat values |
| `--fs-2xl` | 1.75rem / 28px | rank, XP figures |
| `--fs-display` | 2.5rem / 40px | the proofing countdown |

Nav labels go from 10.4 px to 14 px. Line height 1.55 for body, 1.25 for
headings and anything tabular.

---

## 4. Navigation and layout

Two layouts from one markup, switched at 900 px. All nine destinations reachable
in both — this is the point of the exercise.

### 4.1 Mobile (< 900 px)

Bottom bar keeps **five** primary destinations (Today, Starters, Proof, Bakes,
Recipes) and gains a real **More** sheet — a slide-up panel listing Inventory,
Badges, Ranking and Settings with icon, label and one-line description. Not a
redirect to Settings, which is what "More" does today.

Targets go to a minimum 44×44 px. The bar keeps its `env(safe-area-inset-bottom)`
padding.

### 4.2 Desktop (≥ 900 px)

```
┌──────────────┬────────────────────────────────────────┐
│ 🍞 Sourdough │  Today            🏆 Home Baker  🔔    │
├──────────────┼────────────────────────────────────────┤
│ ▸ Today      │ ┌───────────┐ ┌───────────┐            │
│   Starters   │ │ PROOFING  │ │ FEED DUE  │            │
│   Proofing   │ │  2h 14m   │ │  Gerald   │            │
│   Bakes      │ │ ▓▓▓▓▓░░░  │ │  [Feed]   │            │
│   Recipes    │ └───────────┘ └───────────┘            │
│   Inventory  │ ┌───────────┐ ┌───────────┐            │
│   Badges     │ │ STREAK 21 │ │ RANK #1   │            │
│   Ranking    │ └───────────┘ └───────────┘            │
│   Settings   │                                        │
│ ──────────── │                                        │
│ @demo_baker  │                                        │
└──────────────┴────────────────────────────────────────┘
```

- 240 px sidebar, all nine items, text labels, `aria-current="page"` on the
  active one.
- Content area `max-width: 1120px`, cards in a
  `repeat(auto-fit, minmax(280px, 1fr))` grid so the dashboard, badge grid and
  starter list all reflow instead of stacking.
- Sidebar footer shows handle and tier — the identity affordance the header
  currently squeezes in.

One `<nav>` in the markup, `display` switched by media query. No duplicated
destination list to drift out of sync.

### 4.3 Icons

Replace the six nav emoji with inline SVG `<symbol>`s in a `<defs>` block —
about 1.5 KB total, no extra request, consistent across platforms, and
`currentColor` so they inherit the active state. Emoji stay where they are
genuinely content: achievement glyphs from the API, tier icons.

Every decorative glyph gets `aria-hidden="true"`, and nav buttons get a real
accessible name.

---

## 5. Component pass

| Component | Change |
|---|---|
| `.card` | Softer border, layered shadow, `--radius` 12→14px, 16px padding, hover lift on desktop only |
| `button` | 44px min height, `:focus-visible` ring (2px accent, 2px offset), `:active` press |
| `button.primary` | Dark label in dark mode (the 2.15:1 fix) |
| `input/select/textarea` | 44px min height, `:focus-visible` replaces `:focus` |
| `.pill` | Deeper text colours; 13px floor |
| `.countdown` | 40px, tabular, `--ok` when ready — keep the behaviour, raise the presence |
| `.meter` | 7→10px, subtle gradient fill |
| `.badge` | Locked state via saturation + a lock glyph, not `opacity: 0.55` (which drops contrast below AA) |
| `.lb-row` | 44px rows, `.you` gets a left accent bar as well as a tint |
| `.toast` | Move above the bottom bar on mobile, bottom-right on desktop |
| `.empty` | Icon + explanation + the action that fills it |
| Spinner | Wrapped in `@media (prefers-reduced-motion: no-preference)`; static ring otherwise |

Also: a **theme toggle** (auto / light / dark) in the header, persisted to
`localStorage`, applied as `data-theme` on `<html>` so it overrides the media
query in both directions.

---

## 6. Phases

| # | Phase | Deliverable | Files |
|---|---|---|---|
| 1 | Font | `scripts/build_font.py`, `web/vendor/inter-4.1-latin.woff2`, `@font-face`, SW `SHELL` + `VERSION` bump | 3 + 1 binary |
| 2 | Tokens | Type scale, spacing scale, corrected palette, both themes, `data-theme` override | `app.css` |
| 3 | Navigation | Sidebar + bottom bar + More sheet, SVG icons, all nine destinations, `aria-current` | `app.css`, `index.html`, `app.js` |
| 4 | Layout | Responsive content grid, dashboard as real cards, header restructure, theme toggle | `app.css`, `index.html` |
| 5 | Components | The table in §5, focus states, reduced motion, inline styles moved into classes | `app.css`, `index.html` |
| 6 | Verify | Contrast script, size check, node tests, headless render sweep | `scripts/check_contrast.py`, `scripts/check_shell_size.py`, `web/test/` |

Phases 1–2 are independent. 3 and 4 both touch `index.html` and should land in
order. Each phase leaves the app working — no phase depends on a later one to
render correctly.

`app.js` changes are small and confined: a `MORE_ROUTES` list, a `moreOpen`
flag, a `theme` property with its persistence, and replacing the 9-branch inline
ternary with a `TITLES` map.

---

## 7. Verification

- **`scripts/check_contrast.py`** — parses the custom properties straight out of
  `app.css`, computes every declared pair in both themes, exits non-zero below
  4.5:1. The audit in §2.2 becomes a regression test rather than a one-off.
- **`scripts/check_shell_size.py`** — budgets **transfer** size, not file size.
  This changed during the build: an uncompressed budget treats 36 KB of HTML as
  equal to 54 KB of woff2, when the first compresses to 7.5 KB and the second
  does not compress at all. On the wire the shell is 93 KB and **the font is 58%
  of it** — measuring raw bytes would have pointed the trimming effort at the
  markup and away from the only asset that actually dominates the download. The
  same script fails if any `SHELL` entry is missing, because `cache.addAll()`
  rejects on one 404 and takes the entire offline install with it.
- **`node --test web/test/app.test.mjs`** — the existing 11 must stay green;
  add cases for `MORE_ROUTES` covering every route not in the primary nav (so
  a future route cannot become orphaned again the way three did), and for theme
  persistence.
- **Manual sweep** — all nine views at 375 px, 768 px and 1440 px, in both
  themes, keyboard-only once through.
- **Offline** — DevTools offline, hard reload, confirm the font renders from
  cache and does not fall back.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| 53 KB font on a shell that sells itself on being small | Measured, budgeted, precached; `swap` so first paint is never blank |
| A checked-in binary nobody can regenerate | `build_font.py --check` rebuilds and compares byte-for-byte |
| SW cache invalidation missed on deploy | `VERSION` bump is part of phase 1, not an afterthought |
| Sidebar markup diverging from bottom bar | One `<nav>`, CSS-switched — not two lists |
| Dashboard grid breaking the countdown's live update | Alpine bindings are untouched; only container CSS changes |
| Contrast regressions creeping back | `check_contrast.py` runs in CI alongside ruff and mypy |

---

## 9. Open items

- The Flutter app keeps its own Material theme. Matching it to the new palette
  is a separate, later job — worth doing, not worth blocking this on.
- `manifest.json` `theme_color` is currently a single value and will look wrong
  against one of the two themes. Splitting it needs a `<meta name="theme-color">`
  per `prefers-color-scheme`; folding into phase 4.
- Whether Inventory belongs in the primary five on mobile, demoting Recipes to
  More. Worth revisiting once it is reachable at all and can be observed.
