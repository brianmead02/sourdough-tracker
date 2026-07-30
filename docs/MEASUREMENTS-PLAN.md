# Measurements & Unit Conversion Plan

Let bakers work in the units they own equipment for — cups, ounces, millilitres,
Fahrenheit — without the service ever storing anything but grams and Celsius.

**Status: all five phases built and verified (2026-07-30).**

Built: the pure conversion module (`app/services/measurements/`), the 36-entry
density catalogue, free-text resolution, two tables, a migration,
`sdt seed-measurements`, five endpoints, the `?units=` override, `display`
siblings on three read paths, volume/Fahrenheit accepted on three write paths,
and both clients switched. 288 unit, 262 integration, 24 browser-logic and 16
Dart tests green; 101 endpoints.

Running it live corrected two more things the plan had wrong — see §11.

Fetching the reference chart during phase 2 corrected four densities this plan
had asserted from memory. They are fixed below, and the wrong values are left
visible because the correction is the point:

| | Planned | Actual (charted) |
|---|---|---|
| Bread flour | ~~127~~ | **120 g/cup** |
| Diamond Crystal salt | ~~137~~ | **128 g/cup** (1 tbsp = 8 g) |
| Salt spread | ~~2.1×~~ | **2.25×** |
| Honey | ~~340~~ | **336 g/cup** |
| Rolled oats | ~~89~~ | **113 g/cup** |

The formatting rule in §6.1 needed two more corrections beyond the one this plan
already recorded — see §6.2.

---

## 1. Decisions locked in

| Question | Decision |
|---|---|
| Authority | **Grams stay the truth.** Volume accepted on input, converted immediately; offered on output. Hydration, baker's percentages and the fermentation model never see a volume. |
| Density data | **Code catalogue → DB projection → user overrides.** Same shape as `achievement`: authored in Python, seeded into a table, overridable per user. |
| Unit families | US volume (cup/tbsp/tsp/fl oz), US mass (oz/lb), metric (ml/l/kg), temperature °F |
| Preference | **`user_profile.units` default, `?units=` per request override** |

Non-goals: imperial UK units (a UK fl oz is 28.41 ml, not 29.57), Australian
metric cups (250 ml), storing what the baker typed, or guaranteeing a lossless
round-trip.

---

## 2. The hard part is not unit conversion

Three genuinely different operations get called "conversion", and conflating
them is where this goes wrong:

| Kind | Example | Nature |
|---|---|---|
| mass ↔ mass | g → oz | **Exact ratio.** Defined constants. |
| volume ↔ volume | tsp → ml | **Exact ratio.** Defined constants. |
| temperature | °C → °F | **Affine** — has an offset, so it does not scale. A 5 °C *difference* is not 41 °F. |
| **volume ↔ mass** | cup of rye → g | **Requires a density, per ingredient, and is approximate.** |

Only the last one needs a table, and it is the whole reason this is a project
rather than a function.

### 2.1 How bad the spread is

Grams per US cup, from published charts:

| Ingredient | g/cup | 1 tsp |
|---|---|---|
| water | 236.6 | 4.9 |
| all-purpose flour | 120 | — |
| bread flour | 120 | — |
| whole wheat flour | 113 | — |
| rye flour | 106 | — |
| honey | 336 | 7.0 |
| **table / fine sea salt** | **288** | **6.0** |
| **Diamond Crystal kosher salt** | **128** | **2.67** |

Two things follow.

**Salt cannot have a default.** "1 tsp salt" is 6.0 g or 2.67 g depending on the
brand — a **2.25× difference** in the ingredient that most reliably ruins a loaf
at 2% of flour weight. The catalogue will refuse to convert salt by volume
without an explicit variety match, rather than pick a middle value and be wrong
by 100% half the time.

**Starter cannot be measured by volume at all.** A levain at peak is mostly gas;
the same cup of starter weighs perhaps 60% of what it weighed just after
feeding. Volume for `kind = starter` is refused outright.

**Flour depends on technique, not just type.** The same bread flour is ~120 g/cup
spooned-and-levelled and ~145 g/cup scooped straight from the bag — a 20%
spread, which at 500 g of flour is a different loaf. The catalogue standardises
on **spooned and levelled** and records that choice per entry, because a number
without its method is not reproducible.

### 2.2 Which means conversions must state their confidence

Every conversion returns not just a number but how it was arrived at:

| `basis` | Meaning | Trust |
|---|---|---|
| `exact` | mass↔mass, volume↔volume, temperature | Definitional |
| `catalogue` | matched a named catalogue entry | Good, ±5% |
| `user_override` | matched the baker's own measured density | Best available |
| `kind_default` | fell back to the representative density for flour / liquid / inclusion | Rough, ±20% — flagged in the response |
| *refused* | salt without a variety, or any starter | No number returned |

A client showing a `kind_default` conversion should say so. Silently rendering a
±20% guess as though it were a measurement is the failure mode this whole design
exists to avoid.

### 2.3 The matching problem

`RecipeIngredient.name` is free text (`String(80)`), so "Bread Flour", "bread
flour", "strong white flour" and "AP flour" all have to reach the right row.
Resolution order, first hit wins:

1. **User override** on the normalised slug
2. **Exact slug** match against the catalogue
3. **Alias** match (`strong white flour` → `bread-flour`)
4. **Kind default** — except `salt` and `starter`, which refuse

Normalisation: lowercase, trim, collapse internal whitespace, strip a trailing
`s`, replace spaces with `-`. Deliberately dumb and predictable; no fuzzy
matching, because a wrong match is worse than no match.

---

## 3. Exact constants

Ratios that are defined rather than measured, and should be written at full
precision so nobody has to wonder whether a value was rounded:

```python
GRAMS_PER_OUNCE = Decimal("28.349523125")      # avoirdupois, exact by definition
GRAMS_PER_POUND = Decimal("453.59237")          # exact
ML_PER_US_FL_OZ = Decimal("29.5735295625")      # exact (US gallon = 3.785411784 L)
ML_PER_US_CUP   = Decimal("236.5882365")        # 8 fl oz
ML_PER_US_TBSP  = Decimal("14.78676478125")     # 1/2 fl oz
ML_PER_US_TSP   = Decimal("4.92892159375")      # 1/6 fl oz
ML_PER_US_PINT  = Decimal("473.176473")         # 16 fl oz
ML_PER_US_QUART = Decimal("946.352946")         # 32 fl oz
```

Two notes worth writing down before someone "fixes" them:

- **The US customary cup is 236.5882365 ml, not 240.** 240 ml is the FDA
  *nutrition-labelling* cup. Recipes use customary.
- **Water is taken as 1.000 g/ml.** Its actual density at 20 °C is 0.99821, so
  this is 0.18% high — below the resolution of any kitchen scale, and it matches
  every published chart. Being consistent with the charts matters more here than
  being right in the fourth digit.

Temperature is affine and gets its own code path:

```python
def c_to_f(c: float) -> float: return c * 9 / 5 + 32
def f_to_c(f: float) -> float: return (f - 32) * 5 / 9
```

---

## 4. The catalogue

`app/services/measurements/catalogue.py`, roughly 40 entries:

```python
@dataclass(frozen=True, slots=True)
class IngredientMeasure:
    slug: str                 # "dark-rye-flour"
    name: str                 # "Dark rye flour"
    kind: IngredientKind
    grams_per_cup: float      # the reviewable number; g/ml derived
    aliases: tuple[str, ...]  # ("rye flour", "wholegrain rye")
    method: Method            # spooned_levelled | poured | packed | liquid
    source: str               # where the number came from
    volume_allowed: bool = True
```

`grams_per_cup` rather than g/ml because that is the unit every published chart
uses, which makes the values reviewable against a source. g/ml is derived
(`grams_per_cup / 236.5882365`) and never authored.

`source` is a field, not a comment: a density with no provenance cannot be
checked, and these numbers will be argued about.

Coverage: ~14 flours, ~8 liquids, 4 salts, ~12 inclusions (seeds, nuts, dried
fruit, cocoa), plus `starter` entries that exist only to carry
`volume_allowed = False` and a reason.

---

## 5. Data model

Two tables and one column. No changes to any existing gram field.

**`ingredient_measure`** — projection of the code catalogue, so clients can list
it and overrides can key off it.

| Column | Notes |
|---|---|
| `slug` | PK |
| `name`, `kind`, `grams_per_cup`, `method`, `source`, `volume_allowed` | from code |
| `aliases` | `JSONB` array; a GIN index if lookup by alias ever needs it |

**`user_ingredient_measure`** — per-baker overrides.

| Column | Notes |
|---|---|
| `user_id`, `slug` | composite PK; `slug` FKs `ingredient_measure` |
| `grams_per_cup` | the baker's own measurement |
| `note` | "my local mill's rye, weighed 3×" |

**`user_profile.units`** — `String(8)`, default `'metric'`, values `metric` |
`us`. A column rather than a JSONB preference because it is read on nearly every
response and there is exactly one of it.

Migration follows `954f0440c488` (current head).

**`ingredient_measure` must be added to `PRESERVED_TABLES` in
`tests/conftest.py`.** It is reference data like `achievement`; truncating it
between tests would break the FK from `user_ingredient_measure` and force a
re-seed per test. `user_ingredient_measure` is *not* preserved — it is user data.

---

## 6. The conversion module

`app/services/measurements/` — pure functions, no I/O, per the rule in
[ARCHITECTURE.md](ARCHITECTURE.md#2-layers). The densities arrive as plain
values; the module never touches a session.

```python
def to_grams(value: float, unit: Unit, density: Density | None) -> Conversion
def from_grams(grams: float, unit: Unit, density: Density | None) -> Conversion
def convert_temperature(value: float, frm: TempUnit, to: TempUnit) -> float
def describe(grams: float, ingredient: Density, system: System) -> str
```

`Conversion` carries `value`, `unit`, `basis` and `approximate: bool` — so the
confidence from §2.2 travels with the number instead of being reconstructed by
each caller.

### 6.1 Formatting is its own problem, and the obvious rule is wrong

`500 g ÷ 127 g/cup = 3.937 cups` is a true answer and a useless one. `describe()`
snaps to fractions a real measuring cup can express, then puts the remainder in
the next unit down.

I prototyped this while writing the plan, because the obvious rule fails badly.
**Rounding the first term to the nearest fraction overshoots**, which leaves a
negative remainder, which gets dropped — so `340 g water` renders as `1½ cups`,
**+4.4%**. Fifteen grams of water is 3% hydration on a 500 g loaf. Three rules
fix it, all verified against a table of real quantities:

1. **Floor the first term**, never round it, so the remainder stays positive.
2. **The last rung rounds to nearest**, since there is nothing below it to carry
   a remainder into.
3. **Tablespoons only in halves.** `1⅔ tbsp` is not a measurement anyone can
   make; the same amount as `5 tsp` is. When a tbsp remainder is not a clean
   half, cascade to teaspoons.

Verified output, with what each string re-enters as if a baker typed it back in:

| Grams | Rendered | Re-enters as | Error |
|---|---|---|---|
| 500 g bread flour | `3¾ cups + 3 tbsp` | 500.1 g | +0.0% |
| 1000 g bread flour | `7¾ cups + 2 tbsp` | 1000.1 g | +0.0% |
| 340 g water | `1⅓ cups + 5 tsp` | 340.1 g | +0.0% |
| 102 g dark rye | `1 cup` | 102.0 g | +0.0% |
| 50 g honey | `2 tbsp + 1 tsp` | 49.6 g | −0.8% |
| 7 g Diamond Crystal salt | `2½ tsp` | 7.1 g | +1.9% |
| **10 g fine sea salt** | **`1¾ tsp`** | **10.5 g** | **+5.0%** |

**The worst case is small masses**, and it is not fixable by cleverness: 10 g of
fine salt is 1.667 tsp, and a spoon set has no ⅓ tsp, so ¾ is the closest thing
that exists. Anything under ~15 g should carry a *"weigh this if you can"* hint
rather than pretend the spoon is precise — which is the same conclusion the salt
density spread in §2.1 already forces.

Two terms are preferred. A third is allowed where it genuinely improves
measurability (`1¾ cups + 2 tbsp + 2½ tsp` beats `1¾ cups + 8½ tsp`); the exact
threshold is a phase-1 decision, settled by the test table rather than by taste.

**Display conversion is advisory and does not round-trip exactly.** That is
inherent to volume measurement, not a defect to be solved with more decimal
places — and it is the reason grams stay the stored value.

### 6.2 Two further corrections found while building it

The three rules above were necessary and not sufficient. Building the thing
surfaced two more failures that only appear across the full range of quantities:

**Candidates must be generated from every starting rung, not the largest usable
one.** 10 g of salt is 8.2 ml; starting at tablespoons gives `½ tbsp + ¼ tsp`,
starting at teaspoons gives `1¾ tsp`. Same amount, one term, obviously better —
and unreachable if you only ever start from the largest unit that fits.

**Terms need a per-unit ceiling.** Once every rung was a candidate, the scorer
happily returned `200 tsp` for 500 g of flour: one term, near-zero error, and
completely useless. Measuring sets cascade — 3 tsp to a tablespoon, 4 tablespoons
to a quarter cup — so a term beyond `MAX_PER_TERM` means the wrong unit was
picked. With the ceiling, the same quantity reads `4⅛ cups`.

A third, smaller one: a quantity too small for any spoon now returns **grams**.
1 g of honey is 0.7 ml and the finest graduation is a ¼ tsp at 1.23 ml, so the
old code said `¼ tsp` — **77% high**. A precise gram figure the baker must weigh
beats a spoonful that is confidently wrong.

Measured drift by band, asserted in `tests/test_measurements.py`:

| Quantity | Worst drift |
|---|---|
| 100 g and above | 1.0% |
| 50–100 g | 1.5% |
| 15–50 g | 5.0% |
| below 15 g | 10.0% (then it becomes grams) |

---

## 7. API surface

Four new endpoints, plus a parameter and a field on existing ones.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/measurements/units` | Unit catalogue: symbol, family, exact ratio. Static; cacheable. |
| `GET` | `/measurements/ingredients` | Catalogue with the caller's overrides merged in, `?kind=` filter |
| `POST` | `/measurements/convert` | Batch: a list of `{value, from, to, ingredient?}`, returns `Conversion` each |
| `PUT` | `/measurements/ingredients/{slug}/override` | Set or clear the caller's density |

Batch on `convert` because a client rendering a recipe needs every ingredient at
once, and eight round-trips to convert eight lines is the wrong shape.

**`?units=metric|us`** on the read paths that quote quantities:
`GET /recipes/{id}/scale`, `GET /recipes`, `GET /bakes`, `GET /inventory/items`,
`GET /starters/{id}/suggested-feed`. Absent → the profile default.

Responses gain a **sibling** field rather than changing the existing one:

```json
{ "name": "bread flour", "grams": 500.0,
  "display": { "value": "3¾ cups + 2 tbsp", "basis": "catalogue", "approximate": true } }
```

Additive, so every existing client keeps working and nothing has to be
versioned.

### 7.1 Volume on input

`RecipeIngredientInput` and `InventoryTransactionCreate` gain an optional
`{value, unit, ingredient_slug?}` alternative to the gram field. Exactly one of
the two must be supplied — a `model_validator`, not two independent optional
fields that can disagree. Conversion happens in the route; only grams reach the
service layer.

### 7.2 Temperature needs care

`DoughTemp = Annotated[float, Field(ge=0, le=45)]` — **those bounds are
Celsius**. A baker entering 75 °F would fail validation as out of range, and one
entering 24 believing it is Fahrenheit would silently get a hot dough.

So: a separate optional `dough_temp_f` field, converted then validated against
the same Celsius bounds, and the two are mutually exclusive. Not a `unit`
discriminator on one field — that makes the range check depend on a sibling
value, which is exactly the kind of thing Pydantic makes awkward and reviewers
miss.

---

## 8. Phases

| # | Phase | Deliverable | Depends on |
|---|---|---|---|
| 1 | ✅ Conversion core | `app/services/measurements/` — constants, unit taxonomy, `to_grams`/`from_grams`, temperature, `describe()`. Pure, 48 tests. | — |
| 2 | ✅ Catalogue | 36 sourced entries, `ingredient_measure` + `user_ingredient_measure`, migration `4f2696a207a3`, `sdt seed-measurements`, resolution order from §2.3. 32 further tests. | 1 |
| 3 | ✅ API | **Five** endpoints (a `DELETE` to clear an override reads better than a nullable `PUT`), `user_profile.units`, `?units=`, `display` siblings on **three** read paths | 2 |
| 4 | ✅ Input | Amounts on recipe ingredients (converted to baker's percentages), volume on inventory transactions, `dough_temp_f` / `ambient_temp_f` normalised in-schema | 3 |
| 5 | ✅ Clients | Units card in web Settings and a `SegmentedButton` in the Flutter More tab; `?units=` on reads; `display` rendered with its caveat; free-text amount entry for restocking; °F on both proof forms | 3 |

Phase 1 is worth doing alone: it is where the arithmetic lives, it needs no
database, and it is the part that must be exactly right.

---

## 9. Verification

- **Exact constants asserted against their definitions**, not against each other:
  `16 oz == 1 lb`, `8 fl oz == 1 cup`, `3 tsp == 1 tbsp`, `16 tbsp == 1 cup`.
- **Temperature anchors**: 0 °C = 32 °F, 100 °C = 212 °F, −40 °C = −40 °F, and
  37 °C = 98.6 °F. Plus: a proof estimate given 75.2 °F must equal one given
  24 °C, which is the check that the Q10 model was not disturbed.
- **Every catalogue entry round-trips** g → volume → g within its stated
  tolerance.
- **Density sanity bounds per kind** — flour 80–200 g/cup, liquid 200–360,
  salt 130–300. A typo of `1270` for bread flour must fail the test suite, not
  reach a baker.
- **Aliases are globally unique.** An alias claimed by two entries resolves
  arbitrarily, which is a silent wrong answer; assert the set has no duplicates.
- **Salt and starter refusals are tested**, both by kind default and by an
  unmatched name.
- **`describe()` round-trip error is bounded and asserted.** The table in §6.1
  is the test: each string is re-parsed to grams and the deviation checked. The
  ceiling is **±2% above 15 g** and **±6% below it**, and a regression that
  reintroduces the naive nearest-rounding rule (which gave +4.4% on 340 g of
  water) must fail. Awkward cases pinned explicitly: 0.94 cups, 2.45 tsp,
  exactly 3 cups, and a quantity smaller than the smallest fraction.
- **Additive-response test**: existing recipe/bake/inventory responses keep
  every field they had, so no client breaks.

---

## 10. Risks and open items

| Risk | Mitigation |
|---|---|
| A ±20% `kind_default` rendered as though measured | `basis` and `approximate` on every conversion; clients must show it |
| Bakers treating displayed cups as authoritative and re-entering them | Grams remain stored; §6.1 bounds and tests the drift; UI wording, not just docs |
| Small masses cannot be expressed accurately by volume at all | Under ~15 g the response carries a "weigh this if you can" hint; the error is stated rather than hidden |
| Density values argued about | `source` per entry, and user overrides for anyone who disagrees |
| Alias collisions as the catalogue grows | Uniqueness asserted in tests |
| `dough_temp_f` silently accepted alongside `dough_temp_c` | Mutually exclusive via `model_validator`, tested both ways |

---

## 11. Corrections found by running it

Two defects only appeared once the endpoints were exercised against real data.

**A named salt was being refused.** The catalogue set `volume_allowed = False`
on every salt, which is stricter than §2.1 intended: the hazard is the *bare
word* "salt", not Diamond Crystal. Naming a variety is an unambiguous decision
and now converts normally. What refuses is an unmatched salt name, and the
ambiguous aliases `"salt"` and `"kosher salt"` are deliberately claimed by no
entry, with a test asserting so — if either became an alias the refusal would
never fire and a coin flip between 18 g and 8 g per tablespoon would ship.

**The ounce fallback was 25% wrong on small masses.** Refused ingredients fall
back to ounces, which need no density. But ounces are rendered at quarter-ounce
granularity, so 11.3 g of salt became `0.5 oz` — 14.2 g, **+25.4%**. Quarter
ounces are fine for a loaf's worth of flour and useless below about 50 g. The
mass path now obeys the same `MAX_DRIFT_PCT` ceiling as the volume path and
returns grams instead.

Also worth recording: `display` is additive, but an existing test asserting the
suggested-feed response by **exact dict equality** still failed. Additive means
no field changed, not that a strict-equality client sees nothing. That test now
compares a subset.

### Phase 4: recipes have no gram field

§7.1 assumed `RecipeIngredientInput` had a gram field to offer an alternative to.
It does not — a recipe is stored as **baker's percentages**, so there was nothing
to substitute. The useful feature turned out to be a different one: accept
absolute `amount` + `unit`, convert to grams, and *derive* the percentages. That
is what a baker with measuring cups actually wants, and it saves them working out
70% hydration by hand before they can save a recipe.

Two consequences fell out of it:

* **All-or-nothing per recipe.** Mixing "100%" and "3 cups" in one list has no
  single reading, so it is rejected.
* **Percentage validation moves to the route** in amount mode, because the
  percentages do not exist until densities have been loaded, and a Pydantic
  validator has no database session.

`dough_temp_f` needed `exclude=True` rather than merely being cleared by the
validator: the proofing route spreads the payload straight into the ORM model, so
a leftover key is a `TypeError`. Thirty integration tests found that immediately.

### Phase 5: what the clients could and could not use

`units` was not on `ProfileUpdate`, so the preference was unsaveable - added,
along with `OwnProfile.units` so a client can read it back.

The Flutter app has no inventory or recipes tab, so `display` has nothing to
render there yet; what it gained is the toggle and Fahrenheit entry. The web app
has no recipe *creation* form either, so amount-based recipe entry is API-only
for now. Neither is a gap in the feature - it is where the clients happen to be.

One deliberate refactor: the restock prompt's parsing became an exported
`parseAmount()`, with four browser tests. It is the single place where a baker's
typing turns into a stored quantity, and a misread unit does not display a wrong
number, it saves one. `"7 furlongs"` returns null rather than guessing.

And a display bug the amount entry created: `to_percentages` keeps four decimals
so scaling stays exact, and the UI printed them raw - `90.0563%`. Now rounded for
display only.

---

## 12. Open items

Deliberately deferred:

- **Imperial UK and Australian metric cups.** A UK fl oz is 28.4130625 ml and an
  Australian cup is 250 ml. The service is public and international, so this will
  come up; the `System` enum should be designed to take a third value without a
  migration.
- **Per-recipe authored units.** Rejected for v1 in favour of viewer preference,
  but a `recipe.authored_units` column would let a shared recipe show "as the
  author wrote it" alongside the reader's units.
- **Scooped vs spooned as a user preference.** The catalogue standardises on
  spooned; a baker who scoops is consistently ~20% heavy. A per-user `method`
  preference would fix it and doubles the catalogue's surface, so: later, if
  anyone asks.
