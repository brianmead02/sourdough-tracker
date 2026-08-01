# Imagery Plan

Bringing the three files in `images/` into the app, or deciding not to.

**Status: A and B built (2026-08-01). C and D declined, as recommended.**

Shipped: `scripts/build_images.py` with `--check`, the moody photograph as the
sign-in hero, and the loaf redrawn as a background-free `<symbol>` on all seven
empty states. 27 browser-logic tests (up from 24), all suites green.

Two things the mockups did not predict — see §8.

---

## 1. What is in the folder

| File | Kind | Background | Bytes |
|---|---|---|---|
| `1fYiT6TB.jpg` | photograph, floured boule, soft light | `#d7d7d6` neutral grey | 51,520 |
| `1kuooGk_.jpg` | photograph, boule, hard side light | `#444032` dark warm grey | 56,031 |
| `e5mQs4j3.jpg` | flat vector illustration, cut seeded loaf | `#646462` mid grey | 22,974 |

All three are 640×640. **They are not a set** — two photographs and one
illustration, on three unrelated backgrounds. Used together they read as three
different products, so the first decision is which single direction to take.

---

## 2. Measured, not eyeballed

Backgrounds sampled from the corners; crust tone averaged over the warm pixels.

### 2.1 The photographs sort themselves by theme

| Pair | Ratio | Reads as |
|---|---|---|
| bright photo bg vs `--bg` light `#faf7f2` | **1.35** | a grey block on a warm cream page |
| bright photo bg vs `--bg` dark `#16120e` | 12.94 | a glowing rectangle |
| moody photo bg vs `--surface` dark `#201a15` | **1.66** | nearly seamless |
| moody photo bg vs `--bg` light `#faf7f2` | 9.70 | a dark hole in the page |

So the bright one belongs to a light interface and the moody one to a dark
interface, and **neither works in both**. That is not a flaw in the images; it is
what backgrounds do. Any placement that shows a background has to pick per theme,
or crop the background away.

The 1.35 is the awkward number. It is not enough contrast to look deliberate and
not little enough to disappear — the neutral grey sits just off the app's warm
cream and reads as a mismatch rather than a choice.

### 2.2 The illustration is already on-palette

Its crust averages `#dfb076`, a ratio of **1.09** against the app's dark accent
`#f59e0b` — effectively the same colour. Only its grey backdrop is wrong, and on
flat art a backdrop is removable. That makes it the cheapest of the three to
adopt properly.

### 2.3 Text cannot sit directly on bread

Crust tones are `#9f6f4c`, `#7c5c3f`, `#dfb076` — ratios of **1.16 to 1.21**
against the light accent. Any text over an image needs a scrim, and
`scripts/check_contrast.py` **cannot see this**: it parses custom properties out
of the stylesheet, so an image behind text is invisible to it. Overlay text is a
manual check, permanently.

---

## 3. Budget

The offline shell is at **94,871** of a **130,000** byte transfer budget, leaving
**35,129**. WebP, measured:

| Size | All three | Verdict |
|---|---|---|
| 160 px | 8,358 | 24% of headroom |
| 240 px | 15,740 | 45% |
| **320 px** | **26,102** | **74% — the practical ceiling** |
| 640 px | 107,218 | 3× over |

WebP at 320 px is a 5× saving on the 130,525 bytes of source JPEG.

**Nothing here should join the `SHELL` array by default.** The shell is what a
cold visitor downloads before the app renders; a sign-in illustration does not
need to be in it. Images are `loading="lazy"` and cached by the existing
network-first data rule, which keeps the budget check meaningful.

---

## 4. The four placements

Mocked in both themes in the review page. Summarised:

| | Placement | Verdict |
|---|---|---|
| **A** | Sign-in hero, circular crop | ✅ **built**, moody photograph |
| **B** | Empty states | ✅ **built**, redrawn as SVG |
| **C** | Bake thumbnail placeholder | declined |
| **D** | Dashboard banner | deferred |

### A · Sign-in hero — take it

Replaces the 🍞 emoji on the one screen every new baker sees first. It carries no
data, and it is not in the offline shell. ~20 KB, lazily loaded.

> This section originally claimed a circular crop *removes* the background and
> so needs one image per theme. Building it disproved both halves — see §7. The
> claim is left here because the correction is the useful part.

### B · Empty states — take it, but redraw it

Six dashed boxes say things like "Nothing proofing." The illustration suits these
better than a photograph: it is 5.6 KB, it does not compete with the text, and it
is not pretending to be a real loaf.

The mockup patches its grey backdrop with `mix-blend-mode`, and **that patch is
visibly imperfect on dark** — deliberately left visible in the examples. The
honest version is a background-free **SVG**: roughly 2 KB, sharp at any size, and
able to inherit `currentColor` so it themes itself with no second asset. That is
a redraw, not a conversion.

### C · Bake thumbnail placeholder — skip

Bakes already support real photographs (`bake_photo`, presigned uploads). A stock
loaf in that slot is a photograph of *someone else's bread* standing where the
baker's own belongs, repeated identically down a list of twelve. A neutral icon
says "no photo yet" without the lie.

### D · Dashboard banner — defer

The best-looking option, and it pushes the countdown, feed list and stats below
the fold on a phone. "Today" exists to answer *what needs me now*; a decorative
strip above the answer works against that. Worth revisiting as a desktop-only
flourish once there is a reason beyond appearance.

---

## 5. Phases

| # | Phase | Deliverable |
|---|---|---|
| 1 | ✅ Pipeline | `scripts/build_images.py`, `--check` verified byte-for-byte. Crop coordinates live in the `Asset` record. |
| 2 | ✅ Sign-in hero | **One** image, not one per theme — see §8. 132px circle, `loading="lazy"`, `width`/`height` set. `VERSION` → `v5`. |
| 3 | ✅ Empty-state SVG | 1.6 KB `<symbol id="i-loaf-empty">`, `currentColor` at varying opacity, on all **seven** empty states. |
| 4 | ✅ Verify | Three node guards: every `<img>` has alt/width/height/loading, no image is in `SHELL`, every `<use>` resolves. Each verified to fail when it should. |

Phase 1 is worth doing regardless of which placements are chosen — a checked-in
binary nobody can regenerate is the problem `build_font.py` already solved once.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| Layout shift as images load | `width`/`height` on every `<img>`; a node test asserts it |
| Text over an image failing contrast, invisibly to CI | Scrim required; noted in §2.3 as a permanent manual check |
| Shell budget creeping up | Images stay out of `SHELL`; `check_shell_size.py` reports them separately |
| A redesign that ships to nobody | `VERSION` bump is part of phase 2, not an afterthought |
| The grey-backdrop patch shipping as-is | Phase 3 is a redraw; the blend-mode version is a mockup only |

---

## 7. Corrections found by building it

**The circular crop does not remove the background — it only reduces it.** §4A
claimed otherwise, and the first render disproved it: the photograph's own
horizon, dark olive above and white below, ran straight through the circle. It
read as a badly cropped photo rather than a medallion, and it was worse on dark,
where the white base became a bright crescent.

The fix was not CSS. The loaf's bounding box was measured (x 90–552, y 182–532),
squared off with 4% padding, and that crop now lives in the `Asset` record with
the reasoning attached. The circle is filled with bread. Cost: 10.8 KB → 19.3 KB,
since cropping means more detail per pixel — still lazily loaded and still
outside the shell.

**One photograph serves both themes.** The plan assumed one per theme. Once the
crop leaves almost no backdrop in frame, the moody image works on cream as well
as on near-black, so the second asset was never built.

Also fixed in passing: the sign-in card put a **scrollbar through its own middle**,
because three tabs do not fit 400px and the shared `.tabs` rule scrolls them —
right for the six leaderboard categories, wrong here. Scoped override to wrap.

---

## 8. Open item: provenance

These read as generated stock and the filenames are CDN hashes, so there is no
licence travelling with them. This is a **public, multi-tenant service with open
signup** — imagery on the sign-in screen is seen by everyone, which is a
different exposure from a private tool.

Worth confirming where they came from and what terms they carry before phase 2.
A question about paperwork, not about the design — and the only item here that
cannot be settled by looking at the mockups.
