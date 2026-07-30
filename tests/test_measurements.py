"""Unit tests for conversion and formatting. No database, no I/O.

Three things are being defended here:

1. **The constants are definitional.** `3 tsp == 1 tbsp` must hold exactly, not
   to a tolerance — a tolerance would hide a transcription error, which is the
   likeliest bug in a file of long decimals.
2. **Volume↔mass refuses when it should.** Salt and starter cannot be measured by
   volume honestly, and a plausible-looking wrong number is worse than an error.
3. **`describe()` round-trips within a bounded error.** The naive
   round-to-nearest rule was 4.4% out on 340 g of water; the table below is what
   stops that coming back.
"""

from decimal import Decimal

import pytest

from app.models.recipe import IngredientKind
from app.services.measurements import (
    Basis,
    Density,
    DensityRequiredError,
    IncompatibleUnitsError,
    System,
    Unit,
    VolumeNotAllowedError,
    c_to_f,
    convert,
    convert_temperature,
    describe,
    f_to_c,
    from_grams,
    to_grams,
)
from app.services.measurements.catalogue import BY_SLUG, CATALOGUE, KIND_DEFAULTS
from app.services.measurements.format import FRACTIONS, MAX_DRIFT_PCT, MAX_PER_TERM
from app.services.measurements.resolve import normalise, resolve
from app.services.measurements.units import (
    GRAMS_PER,
    GRAMS_PER_OUNCE,
    GRAMS_PER_POUND,
    ML_PER,
    ML_PER_US_CUP,
    ML_PER_US_FL_OZ,
    ML_PER_US_TBSP,
    ML_PER_US_TSP,
)


def _density(slug: str, *, allow_volume: bool = True) -> Density:
    """Build a test density straight from the catalogue.

    Taking the numbers from CATALOGUE rather than restating them means a
    corrected density cannot leave the tests asserting the old value — which is
    exactly what happened when bread flour was assumed to be 127 g/cup and the
    reference chart said 120.
    """
    entry = BY_SLUG[slug]
    return Density(
        slug=entry.slug,
        grams_per_cup=entry.grams_per_cup,
        basis=Basis.catalogue,
        volume_allowed=entry.volume_allowed if not allow_volume else True,
        reason=entry.reason,
    )


BREAD_FLOUR = _density("bread-flour")
WATER = _density("water")
TABLE_SALT = _density("table-salt", allow_volume=True)
DIAMOND_SALT = _density("diamond-crystal-salt", allow_volume=True)
HONEY = _density("honey")
WHOLE_WHEAT = _density("whole-wheat-flour")
RYE = _density("rye-flour")
STARTER = _density("starter", allow_volume=False)


# --- constants are exact ----------------------------------------------------


def test_us_volume_ladder_is_internally_exact() -> None:
    """Every US volume unit is a defined fraction of the gallon.

    Asserted with `==` on Decimal, not pytest.approx: if someone rounds a
    constant to fewer digits these become false, which is the point.
    """
    assert ML_PER_US_TSP * 3 == ML_PER_US_TBSP
    assert ML_PER_US_TBSP * 2 == ML_PER_US_FL_OZ
    assert ML_PER_US_FL_OZ * 8 == ML_PER_US_CUP
    assert ML_PER_US_TBSP * 16 == ML_PER_US_CUP
    assert ML_PER_US_TSP * 48 == ML_PER_US_CUP
    assert ML_PER[Unit.pint] * 2 == ML_PER[Unit.quart]


def test_us_mass_is_exact() -> None:
    assert GRAMS_PER_OUNCE * 16 == GRAMS_PER_POUND
    assert Decimal("453.59237") == GRAMS_PER_POUND
    assert GRAMS_PER[Unit.kilogram] == 1000


def test_the_cup_is_customary_not_the_labelling_cup() -> None:
    """236.588 ml, not 240. The 240 ml cup is for nutrition labels."""
    assert Decimal("236.5882365") == ML_PER_US_CUP
    assert ML_PER_US_CUP != 240


# --- mass conversions are exact and reversible ------------------------------


@pytest.mark.parametrize(
    ("grams", "unit", "expected"),
    [
        (1000.0, Unit.kilogram, 1.0),
        (float(GRAMS_PER_POUND), Unit.pound, 1.0),
        (float(GRAMS_PER_OUNCE), Unit.ounce, 1.0),
        (500.0, Unit.gram, 500.0),
    ],
)
def test_mass_round_trips_exactly(grams: float, unit: Unit, expected: float) -> None:
    out = from_grams(grams, unit)
    assert out.value == pytest.approx(expected)
    assert out.basis is Basis.exact
    assert out.approximate is False
    assert to_grams(out.value, unit).value == pytest.approx(grams)


def test_mass_needs_no_density() -> None:
    """The point of offering oz/lb: it works for any ingredient, always."""
    assert to_grams(1.0, Unit.pound).value == pytest.approx(453.59237)
    assert from_grams(1000.0, Unit.ounce, density=None).basis is Basis.exact


def test_volume_to_volume_needs_no_density() -> None:
    assert convert(1.0, Unit.cup, Unit.tablespoon).value == pytest.approx(16.0)
    assert convert(3.0, Unit.teaspoon, Unit.tablespoon).value == pytest.approx(1.0)
    assert convert(1.0, Unit.litre, Unit.millilitre).value == pytest.approx(1000.0)


# --- volume needs a density -------------------------------------------------


def test_volume_without_density_is_refused() -> None:
    with pytest.raises(DensityRequiredError):
        to_grams(1.0, Unit.cup)
    with pytest.raises(DensityRequiredError):
        from_grams(500.0, Unit.cup)


def test_one_cup_of_water_is_the_cup_itself() -> None:
    assert to_grams(1.0, Unit.cup, WATER).value == pytest.approx(236.588, abs=0.01)


def test_flour_and_water_differ_for_the_same_cup() -> None:
    flour = to_grams(1.0, Unit.cup, BREAD_FLOUR).value
    water = to_grams(1.0, Unit.cup, WATER).value
    assert flour == pytest.approx(120.0)
    assert water / flour == pytest.approx(1.97, abs=0.01)


def test_the_salt_spread_is_real() -> None:
    """One tablespoon is 18 g or 8 g depending on the brand.

    This is the number that justifies refusing a salt default: at 2% of flour
    weight, picking the wrong one is a 2.1-fold error in the ingredient that
    most reliably ruins a loaf.
    """
    fine = to_grams(1.0, Unit.tablespoon, TABLE_SALT).value
    diamond = to_grams(1.0, Unit.tablespoon, DIAMOND_SALT).value
    assert fine == pytest.approx(18.0, abs=0.01)
    assert diamond == pytest.approx(8.0, abs=0.01)
    assert fine / diamond == pytest.approx(2.25, abs=0.01)


def test_starter_refuses_volume_with_a_reason() -> None:
    with pytest.raises(VolumeNotAllowedError, match="mostly gas"):
        to_grams(1.0, Unit.cup, STARTER)
    with pytest.raises(VolumeNotAllowedError):
        from_grams(200.0, Unit.cup, STARTER)


def test_approximate_conversions_say_so() -> None:
    volume = to_grams(1.0, Unit.cup, BREAD_FLOUR)
    assert volume.approximate is True
    assert volume.basis is Basis.catalogue
    assert volume.source_slug == "bread-flour"

    mass = to_grams(1.0, Unit.ounce)
    assert mass.approximate is False
    assert mass.basis is Basis.exact


def test_user_override_beats_catalogue_in_the_result() -> None:
    mine = Density("rye-flour", 96.0, Basis.user_override)
    assert to_grams(1.0, Unit.cup, mine).basis is Basis.user_override


def test_cross_family_conversion_goes_through_grams() -> None:
    out = convert(1.0, Unit.cup, Unit.ounce, BREAD_FLOUR)
    assert out.value == pytest.approx(120.0 / float(GRAMS_PER_OUNCE))
    assert out.approximate is True
    assert out.basis is Basis.catalogue


# --- temperature ------------------------------------------------------------


@pytest.mark.parametrize(
    ("celsius", "fahrenheit"),
    [(0.0, 32.0), (100.0, 212.0), (-40.0, -40.0), (37.0, 98.6), (24.0, 75.2)],
)
def test_temperature_anchors(celsius: float, fahrenheit: float) -> None:
    assert c_to_f(celsius) == pytest.approx(fahrenheit)
    assert f_to_c(fahrenheit) == pytest.approx(celsius)


def test_temperature_is_affine_not_a_ratio() -> None:
    """A 20 °C rise is a 36 °F rise, not 68.

    Routing temperature through the ratio table would produce plausible, wrong
    numbers — and the Q10 fermentation model consumes this value.
    """
    assert c_to_f(20.0) == pytest.approx(68.0)
    assert c_to_f(40.0) - c_to_f(20.0) == pytest.approx(36.0)
    assert c_to_f(40.0) != pytest.approx(2 * c_to_f(20.0))


def test_temperature_does_not_cross_into_mass_or_volume() -> None:
    with pytest.raises(IncompatibleUnitsError):
        to_grams(20.0, Unit.celsius)
    with pytest.raises(IncompatibleUnitsError):
        from_grams(500.0, Unit.fahrenheit)
    with pytest.raises(IncompatibleUnitsError):
        convert(20.0, Unit.celsius, Unit.gram)
    with pytest.raises(IncompatibleUnitsError):
        convert_temperature(20.0, Unit.celsius, Unit.cup)


def test_same_temperature_unit_is_identity() -> None:
    assert convert_temperature(21.5, Unit.celsius, Unit.celsius) == 21.5


# --- formatting -------------------------------------------------------------


def test_metric_is_exact_and_needs_no_density() -> None:
    assert describe(500.0, None, System.metric).text == "500 g"
    assert describe(1500.0, None, System.metric).text == "1.5 kg"
    assert describe(7.5, None, System.metric).text == "7.5 g"
    assert describe(500.0, None, System.metric).drift_pct == 0.0


#: Every row was checked by hand. `grams` is what the string weighs if measured
#: exactly as written — the number that matters, because a baker following the
#: string gets that and not what they asked for.
RENDER_CASES = [
    (500.0, BREAD_FLOUR, "4⅛ cups", 6.3),
    (1000.0, BREAD_FLOUR, "8⅓ cups", 0.1),
    (120.0, BREAD_FLOUR, "1 cup", 0.1),
    (340.0, WATER, "1⅓ cups + 1½ tbsp", 3.0),
    (750.0, WATER, "3⅛ cups + ½ tbsp", 4.1),
    (106.0, RYE, "1 cup", 0.1),
    (102.0, RYE, "¾ cup + 3½ tbsp", 0.9),
    (218.0, WHOLE_WHEAT, "1¾ cups + 3 tbsp", 1.2),
    (50.0, HONEY, "⅛ cup + 1¼ tsp", 1.0),
    (7.0, DIAMOND_SALT, "2½ tsp", 0.5),
    (10.0, TABLE_SALT, "1¾ tsp", 0.7),
    (3.0, TABLE_SALT, "½ tsp", 0.1),
]


@pytest.mark.parametrize(("grams", "density", "text", "tolerance"), RENDER_CASES)
def test_describe_renders_measurable_quantities(
    grams: float, density: Density, text: str, tolerance: float
) -> None:
    out = describe(grams, density, System.us)
    assert out.text == text
    assert out.grams == pytest.approx(grams, abs=tolerance)


def test_describe_never_offers_an_unmeasurable_fraction() -> None:
    """Only graduations that exist on a real measuring set may appear."""
    for grams in range(1, 1200, 7):
        for density in (BREAD_FLOUR, WATER, HONEY, WHOLE_WHEAT, RYE):
            out = describe(float(grams), density, System.us)
            for term in out.terms:
                assert term.fraction in FRACTIONS[term.unit], (
                    f"{out.text} uses {term.fraction} of a {term.unit.value}, "
                    f"which no measuring set has"
                )


def test_describe_never_says_an_absurd_number_of_small_units() -> None:
    """200 tsp is arithmetically perfect and nobody would ever measure it.

    Measuring sets cascade - 3 tsp to a tablespoon, 4 tablespoons to a quarter
    cup - so a term past its ceiling means the wrong unit was chosen.
    """
    for grams in range(1, 2000, 11):
        for density in (BREAD_FLOUR, WATER, HONEY, WHOLE_WHEAT, RYE, TABLE_SALT):
            out = describe(float(grams), density, System.us)
            for term in out.terms:
                assert term.amount <= MAX_PER_TERM[term.unit], (
                    f"{out.text} says {term} - a larger unit belongs here"
                )


def test_amounts_of_one_or_less_are_singular() -> None:
    """An eighth of a cup is a cup, not cups."""
    assert describe(30.0, BREAD_FLOUR, System.us).text.endswith("cup")
    assert describe(120.0, BREAD_FLOUR, System.us).text == "1 cup"
    assert "cups" in describe(500.0, BREAD_FLOUR, System.us).text


#: Measured ceilings, not aspirations. Accuracy improves with quantity because a
#: fixed graduation is a smaller share of a bigger amount, so the bound is stated
#: per band. Tightening any of these numbers means the algorithm improved;
#: exceeding one means it regressed.
DRIFT_BANDS = [(100, 2000, 1.0), (50, 100, 1.5), (15, 50, 5.0), (1, 15, 10.0)]


@pytest.mark.parametrize(("low", "high", "ceiling"), DRIFT_BANDS)
def test_describe_drift_stays_within_its_band(low: int, high: int, ceiling: float) -> None:
    """The naive nearest-rounding rule was 4.4% out on 340 g of water.

    Nothing may exceed MAX_DRIFT_PCT, because past that `describe` abandons volume
    and returns grams — a precise figure beats a confidently wrong spoonful.
    """
    worst = 0.0
    culprit = ""
    for grams in range(low, high):
        for density in (BREAD_FLOUR, WATER, HONEY, WHOLE_WHEAT, RYE, TABLE_SALT):
            out = describe(float(grams), density, System.us)
            if abs(out.drift_pct) > worst:
                worst, culprit = abs(out.drift_pct), f"{grams} g {density.slug} -> {out.text}"
    assert worst <= ceiling, f"worst drift in {low}-{high} g was {worst:.2f}% ({culprit})"
    assert worst <= MAX_DRIFT_PCT


def test_naive_nearest_rounding_would_fail_this_case() -> None:
    """Pins the specific regression: 340 g of water must not render as 1½ cups.

    That was the original rule's output, 4.4% high — 15 g of water, or 3%
    hydration on a 500 g loaf.
    """
    out = describe(340.0, WATER, System.us)
    assert out.text != "1½ cups"
    assert abs(out.drift_pct) < 1.0


def test_a_quantity_too_small_for_a_spoon_is_given_in_grams() -> None:
    """1 g of honey is 0.7 ml. The smallest graduation is a ¼ tsp at 1.23 ml, so
    "¼ tsp" would be 77% high — worse than useless, because it looks measured."""
    out = describe(1.0, HONEY, System.us)
    assert out.text == "1.0 g"
    assert out.terms == ()
    assert out.advise_weighing is True
    assert out.approximate is False
    assert out.drift_pct == 0.0


def test_small_quantities_advise_weighing() -> None:
    assert describe(10.0, TABLE_SALT, System.us).advise_weighing is True
    assert describe(500.0, BREAD_FLOUR, System.us).advise_weighing is False


def test_us_falls_back_to_exact_mass_when_volume_is_refused() -> None:
    """Refusing volume must not mean refusing to answer.

    Ounces need no density, so a starter or an unmatched salt still gets a
    precise rendering — a better outcome than an error the client has to handle.
    """
    out = describe(200.0, STARTER, System.us)
    assert "oz" in out.text
    assert out.basis is Basis.exact
    assert out.approximate is False
    assert out.grams == pytest.approx(200.0, abs=2.0)

    no_density = describe(500.0, None, System.us)
    assert "lb" in no_density.text


def test_us_mass_uses_pounds_above_a_pound() -> None:
    assert describe(float(GRAMS_PER_POUND), None, System.us).text == "1 lb"
    assert describe(1000.0, None, System.us).text.startswith("2 lb")


def test_the_smallest_expressible_quantity_is_the_boundary() -> None:
    """A quarter teaspoon is the finest thing offered, so it is the dividing line.

    Exactly ¼ tsp of fine salt (1.5 g) renders as a spoon measurement; anything
    materially below it becomes grams, because rounding up to ¼ tsp would be a
    large relative lie about a small quantity.
    """
    quarter_tsp_of_salt = BY_SLUG["table-salt"].grams_per_cup / 48 / 4  # 1.5 g
    on_the_line = describe(quarter_tsp_of_salt, TABLE_SALT, System.us)
    assert on_the_line.text == "¼ tsp"
    assert on_the_line.terms

    below = describe(0.5, TABLE_SALT, System.us)
    assert below.terms == ()
    assert below.text == "0.5 g"
    assert below.advise_weighing is True


# --- catalogue integrity ----------------------------------------------------
#
# These stop a transcription error reaching a baker. Every density came from a
# published chart, and the likeliest bug in such a table is a digit.


def test_slugs_are_unique() -> None:
    slugs = [entry.slug for entry in CATALOGUE]
    assert len(slugs) == len(set(slugs))


def test_no_alias_is_claimed_by_two_ingredients() -> None:
    """An alias two entries both claim resolves arbitrarily.

    That is a silently wrong answer rather than an error - "rye flour" landing on
    rice flour half the time - so make it impossible by construction.
    """
    owners: dict[str, str] = {}
    for entry in CATALOGUE:
        for key in {normalise(alias) for alias in entry.aliases} | {normalise(entry.name)}:
            previous = owners.get(key)
            assert previous in (None, entry.slug), (
                f"{key!r} is claimed by both {previous} and {entry.slug}"
            )
            owners[key] = entry.slug


def test_no_alias_is_redundant() -> None:
    """Normalisation already strips noise words and plurals.

    Listing "warm water" when "water" is the name adds nothing and is one more
    string that could later collide with a real ingredient.
    """
    for entry in CATALOGUE:
        seen = {normalise(entry.name)}
        for alias in entry.aliases:
            key = normalise(alias)
            assert key not in seen, (
                f"{entry.slug}: alias {alias!r} normalises to {key!r}, which is "
                f"already covered - remove it"
            )
            seen.add(key)


#: A typo of 1200 for 120 must fail the suite, not reach a recipe. Bounds are
#: generous: they catch lost or extra digits, they do not adjudicate sources.
SANE_RANGES = {
    IngredientKind.flour: (80.0, 200.0),
    IngredientKind.liquid: (190.0, 360.0),
    IngredientKind.salt: (120.0, 300.0),
    IngredientKind.inclusion: (60.0, 250.0),
}


def test_every_density_is_physically_plausible() -> None:
    for entry in CATALOGUE:
        if entry.kind is IngredientKind.starter:
            continue
        low, high = SANE_RANGES[entry.kind]
        assert low <= entry.grams_per_cup <= high, (
            f"{entry.slug} is {entry.grams_per_cup} g/cup, outside {low}-{high}"
        )


def test_every_entry_records_where_its_number_came_from() -> None:
    for entry in CATALOGUE:
        assert entry.source, f"{entry.slug} has no source"


def test_starter_refuses_volume_with_an_explanation() -> None:
    """Starter is the only kind refused at the catalogue level.

    A named salt is an unambiguous choice and converts normally; it is the bare
    word "salt" that refuses, and that happens during resolution rather than here.
    """
    for entry in CATALOGUE:
        if entry.kind is IngredientKind.starter:
            assert entry.volume_allowed is False, f"{entry.slug} must not allow volume"
            assert entry.reason, f"{entry.slug} refuses volume without saying why"


def test_named_salts_convert_but_ambiguous_ones_do_not() -> None:
    """The 2.25-fold spread is between brands, so the brand is what resolves it.

    "Diamond Crystal" is a decision; "salt" and "kosher salt" are coin flips
    between 18 g and 8 g per tablespoon, and guessing there is the whole hazard.
    """
    for named in ("table salt", "diamond crystal", "morton kosher", "fine sea salt"):
        density = resolve(named, IngredientKind.salt)
        assert density is not None, named
        assert density.volume_allowed is True, f"{named} is specific and should convert"

    for ambiguous in ("salt", "kosher salt", "some other salt"):
        density = resolve(ambiguous, IngredientKind.salt)
        assert density is not None, ambiguous
        assert density.volume_allowed is False, f"{ambiguous} must not be guessed at"
        assert "2.25" in (density.reason or "")


def test_a_small_mass_is_not_rendered_in_quarter_ounces() -> None:
    """11 g rounds to 0.5 oz, which is 25% high - grams instead.

    The ounce fallback exists so a refused ingredient still gets an answer, but
    quarter-ounce granularity is only usable at a loaf's scale.
    """
    out = describe(11.3, resolve("salt", IngredientKind.salt), System.us)
    assert "oz" not in out.text
    assert out.drift_pct == pytest.approx(0.0)


def test_kind_defaults_exist_and_exclude_the_dangerous_kinds() -> None:
    for slug in KIND_DEFAULTS.values():
        assert slug in BY_SLUG
        assert BY_SLUG[slug].volume_allowed
    assert IngredientKind.salt not in KIND_DEFAULTS
    assert IngredientKind.starter not in KIND_DEFAULTS


def test_water_is_the_physical_cup_not_the_bakers_convention() -> None:
    """The reference chart says 227 g; a cup of water actually weighs 236.6 g.

    227 is "a pint's a pound" - a cup treated as 8 avoirdupois ounces. Hydration
    is this service's central calculation, so 4% is not acceptable in it.
    """
    assert BY_SLUG["water"].grams_per_cup == pytest.approx(236.588, abs=0.01)
    assert BY_SLUG["water"].grams_per_cup != 227


def test_one_cup_of_bread_flour_is_the_charted_120_grams() -> None:
    """Pins a real correction: 127 was assumed, the chart says 120."""
    assert BY_SLUG["bread-flour"].grams_per_cup == 120


# --- resolution -------------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("Bread Flour", "bread-flour"),
        ("bread flour", "bread-flour"),
        ("strong white flour", "bread-flour"),
        ("  Organic  Whole-Wheat Flour ", "whole-wheat-flour"),
        ("wholemeal flour", "whole-wheat-flour"),
        ("sultanas", "raisins"),
        ("warm water", "water"),
        ("Tipo 00", "00-flour"),
        ("pepitas", "pumpkin-seeds"),
    ],
)
def test_resolution_finds_the_right_ingredient(written: str, expected: str) -> None:
    density = resolve(written, IngredientKind.flour)
    assert density is not None
    assert density.slug == expected


def test_unmatched_flour_falls_back_to_the_kind_default_and_says_so() -> None:
    density = resolve("unobtainium flour", IngredientKind.flour)
    assert density is not None
    assert density.basis is Basis.kind_default
    assert density.slug == KIND_DEFAULTS[IngredientKind.flour]


def test_unmatched_name_with_no_kind_resolves_to_nothing() -> None:
    assert resolve("mystery powder") is None


def test_an_unnamed_salt_resolves_but_refuses_volume() -> None:
    density = resolve("salt", IngredientKind.salt)
    assert density is not None
    assert density.volume_allowed is False
    assert density.reason is not None
    with pytest.raises(VolumeNotAllowedError):
        to_grams(1.0, Unit.teaspoon, density)


def test_an_unknown_salt_still_refuses_rather_than_guessing() -> None:
    density = resolve("himalayan pink rock salt", IngredientKind.salt)
    assert density is not None
    assert density.volume_allowed is False
    assert "2.25" in (density.reason or "")


def test_salt_is_never_reachable_through_an_ambiguous_alias() -> None:
    """ "salt" and "kosher salt" must not be aliases of any specific variety.

    If they were, the refusal would never fire and a coin flip would ship.
    """
    for entry in CATALOGUE:
        normalised = {normalise(alias) for alias in entry.aliases}
        assert "salt" not in normalised, f"{entry.slug} claims the bare word 'salt'"
        assert "kosher salt" not in normalised, f"{entry.slug} claims 'kosher salt'"


def test_starter_refuses_however_it_is_written() -> None:
    for written in ("starter", "levain", "my sourdough starter", "leaven"):
        density = resolve(written, IngredientKind.starter)
        assert density is not None, written
        assert density.volume_allowed is False, written


def test_a_user_override_wins_over_the_catalogue() -> None:
    mine = resolve("rye flour", IngredientKind.flour, overrides={"rye-flour": 96.0})
    assert mine is not None
    assert mine.basis is Basis.user_override
    assert mine.grams_per_cup == 96.0


def test_an_override_cannot_make_starter_measurable_by_volume() -> None:
    """No amount of careful weighing makes a peaked levain's volume meaningful."""
    density = resolve("starter", IngredientKind.starter, overrides={"starter": 240.0})
    assert density is not None
    assert density.volume_allowed is False


def test_normalisation_is_stable_and_predictable() -> None:
    assert normalise("  BREAD   flour ") == "bread flour"
    assert normalise("Whole-Wheat Flour") == "wheat flour"
    assert normalise("sultanas") == "sultana"


def test_normalisation_is_idempotent() -> None:
    """Both sides of a comparison get normalised, so it must be a fixed point.

    The crude plural rule turns "molasses" into "molasse", which is fine only
    because the catalogue name is put through the same function.
    """
    for written in ("Molasses", "sultanas", "Bread Flour", "pepitas", "Tipo 00"):
        once = normalise(written)
        assert normalise(once) == once, written


def test_every_catalogue_name_resolves_to_itself() -> None:
    """The display name must always find its own entry.

    Cheap, and it catches a normalisation change that silently orphans an
    ingredient - "molasses" becoming unreachable, for instance.
    """
    for entry in CATALOGUE:
        found = resolve(entry.name, entry.kind)
        assert found is not None, entry.name
        assert found.slug == entry.slug, f"{entry.name!r} resolved to {found.slug}"


def test_every_alias_resolves_to_its_own_entry() -> None:
    for entry in CATALOGUE:
        for alias in entry.aliases:
            found = resolve(alias, entry.kind)
            assert found is not None, alias
            assert found.slug == entry.slug, f"{alias!r} resolved to {found.slug}"
