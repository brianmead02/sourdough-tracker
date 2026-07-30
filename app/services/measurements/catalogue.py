"""Ingredient densities: the only data volume↔mass conversion needs.

Values are transcribed from the King Arthur Baking ingredient weight chart,
which is the de facto reference in English-language baking and, crucially,
states its own measuring method: **spooned into the cup and levelled**, never
scooped. The same bread flour scooped from the bag is ~20% heavier, which is a
different loaf. Every entry records its `source` so a number can be checked
rather than argued about.

Two deliberate departures from that chart, both documented on the entries:

* **Water is 236.6 g/cup here, not the chart's 227.** 227 g is the old "a pint's
  a pound" convention — treating a cup as 8 *avoirdupois* ounces. Physically, a
  US cup holds 236.588 ml and water is ~1 g/ml, so a baker measuring a cup of
  water puts 236.6 g in the bowl. Hydration is this service's central
  calculation and a 4% error in the water is not acceptable in it.
* **Salt and starter refuse volume entirely.** See `VolumeNotAllowedError`.

Entries not in the chart carry a different `source`, and there are deliberately
few of them.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.recipe import IngredientKind
from app.services.measurements.units import ML_PER_US_CUP

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

KING_ARTHUR = "King Arthur Baking ingredient weight chart"


class Method(enum.StrEnum):
    """How the reference filled the cup. A density without this is unreproducible."""

    spooned_levelled = "spooned_levelled"
    poured = "poured"
    packed = "packed"
    liquid = "liquid"
    not_applicable = "not_applicable"


@dataclass(frozen=True, slots=True)
class IngredientMeasure:
    slug: str
    name: str
    kind: IngredientKind
    grams_per_cup: float
    method: Method
    source: str
    aliases: tuple[str, ...] = ()
    volume_allowed: bool = True
    reason: str | None = None
    """Why volume is refused. Shown to the baker, not swallowed."""


#: A cup of water, physically. See the module docstring for why this differs
#: from the reference chart.
WATER_GRAMS_PER_CUP = float(ML_PER_US_CUP)

F = IngredientKind.flour
L = IngredientKind.liquid
S = IngredientKind.salt
I = IngredientKind.inclusion  # noqa: E741 - reads better than INC in the table below
ST = IngredientKind.starter

CATALOGUE: tuple[IngredientMeasure, ...] = (
    # --- flours -------------------------------------------------------------
    IngredientMeasure(
        "all-purpose-flour",
        "All-purpose flour",
        F,
        120,
        Method.spooned_levelled,
        KING_ARTHUR,
        ("ap flour", "plain flour", "white flour"),
    ),
    IngredientMeasure(
        "bread-flour",
        "Bread flour",
        F,
        120,
        Method.spooned_levelled,
        KING_ARTHUR,
        ("strong white flour", "strong flour", "high gluten flour"),
    ),
    IngredientMeasure(
        "whole-wheat-flour",
        "Whole wheat flour",
        F,
        113,
        Method.spooned_levelled,
        KING_ARTHUR,
        ("wholemeal flour", "wholewheat flour", "whole grain flour"),
    ),
    IngredientMeasure(
        "rye-flour",
        "Rye flour",
        F,
        106,
        Method.spooned_levelled,
        KING_ARTHUR,
        ("dark rye flour", "light rye flour", "wholegrain rye"),
    ),
    IngredientMeasure(
        "semolina-flour",
        "Semolina flour",
        F,
        163,
        Method.spooned_levelled,
        KING_ARTHUR,
        ("semolina",),
    ),
    IngredientMeasure(
        "spelt-flour", "Spelt flour", F, 99, Method.spooned_levelled, KING_ARTHUR, ("spelt",)
    ),
    IngredientMeasure(
        "durum-flour", "Durum flour", F, 124, Method.spooned_levelled, KING_ARTHUR, ("durum",)
    ),
    IngredientMeasure(
        "buckwheat-flour",
        "Buckwheat flour",
        F,
        120,
        Method.spooned_levelled,
        KING_ARTHUR,
        ("buckwheat",),
    ),
    IngredientMeasure("oat-flour", "Oat flour", F, 92, Method.spooned_levelled, KING_ARTHUR, ()),
    IngredientMeasure("rice-flour", "Rice flour", F, 142, Method.spooned_levelled, KING_ARTHUR, ()),
    IngredientMeasure(
        "cornmeal",
        "Cornmeal",
        F,
        138,
        Method.spooned_levelled,
        KING_ARTHUR,
        ("polenta", "maize meal"),
    ),
    IngredientMeasure(
        "00-flour",
        "'00' pizza flour",
        F,
        116,
        Method.spooned_levelled,
        KING_ARTHUR,
        ("00 flour", "doppio zero", "tipo 00"),
    ),
    IngredientMeasure(
        "pizza-flour-blend", "Pizza flour blend", F, 124, Method.spooned_levelled, KING_ARTHUR, ()
    ),
    # --- liquids ------------------------------------------------------------
    IngredientMeasure(
        "water",
        "Water",
        L,
        WATER_GRAMS_PER_CUP,
        Method.liquid,
        "1 US cup = 236.5882365 ml; water taken as 1.000 g/ml",
        (),
    ),
    IngredientMeasure("milk", "Milk", L, 227, Method.liquid, KING_ARTHUR, ("semi skimmed milk",)),
    IngredientMeasure("buttermilk", "Buttermilk", L, 227, Method.liquid, KING_ARTHUR, ()),
    IngredientMeasure(
        "honey", "Honey", L, 336, Method.liquid, f"{KING_ARTHUR} (1 tbsp = 21 g)", ()
    ),
    IngredientMeasure(
        "molasses",
        "Molasses",
        L,
        340,
        Method.liquid,
        f"{KING_ARTHUR} (1/4 cup = 85 g)",
        ("treacle",),
    ),
    IngredientMeasure(
        "maple-syrup", "Maple syrup", L, 312, Method.liquid, f"{KING_ARTHUR} (1/2 cup = 156 g)", ()
    ),
    IngredientMeasure(
        "olive-oil",
        "Olive oil",
        L,
        200,
        Method.liquid,
        f"{KING_ARTHUR} (1/4 cup = 50 g)",
        ("oil", "vegetable oil"),
    ),
    # --- salt ---------------------------------------------------------------
    # A tablespoon of table salt is 18 g and a tablespoon of Diamond Crystal is
    # 8 g - a 2.25-fold difference in the ingredient that ruins a loaf fastest.
    # Naming one of these is an unambiguous choice and converts normally. It is
    # the bare word "salt" that refuses, in resolve._refusal, because guessing
    # there is a coin flip between 18 and 8. Note what is deliberately *not* an
    # alias: "salt" and "kosher salt", both of which are the ambiguous cases.
    IngredientMeasure(
        "table-salt",
        "Table salt",
        S,
        288,
        Method.poured,
        f"{KING_ARTHUR} (1 tbsp = 18 g)",
        ("iodised salt", "fine salt"),
    ),
    IngredientMeasure(
        "fine-sea-salt",
        "Fine sea salt",
        S,
        288,
        Method.poured,
        "matches table salt by grain size",
        ("sea salt",),
    ),
    IngredientMeasure(
        "diamond-crystal-salt",
        "Diamond Crystal kosher salt",
        S,
        128,
        Method.poured,
        f"{KING_ARTHUR} (1 tbsp = 8 g)",
        ("diamond crystal", "dc kosher"),
    ),
    IngredientMeasure(
        "morton-kosher-salt",
        "Morton kosher salt",
        S,
        230,
        Method.poured,
        "manufacturer stated 1 tsp = 4.8 g",
        ("morton kosher",),
    ),
    # --- starter ------------------------------------------------------------
    IngredientMeasure(
        "starter",
        "Sourdough starter",
        ST,
        0.0,
        Method.not_applicable,
        "not measurable by volume",
        ("levain", "leaven"),
        volume_allowed=False,
        reason="a levain at peak is mostly gas, so its volume says nothing "
        "about how much of it there is; weigh it",
    ),
    # --- inclusions ---------------------------------------------------------
    IngredientMeasure(
        "granulated-sugar",
        "Granulated sugar",
        I,
        198,
        Method.poured,
        KING_ARTHUR,
        ("sugar", "caster sugar", "white sugar"),
    ),
    IngredientMeasure(
        "brown-sugar",
        "Brown sugar",
        I,
        213,
        Method.packed,
        f"{KING_ARTHUR} (packed)",
        ("light brown sugar", "dark brown sugar"),
    ),
    IngredientMeasure(
        "rolled-oats",
        "Rolled oats",
        I,
        113,
        Method.poured,
        KING_ARTHUR,
        ("oats", "porridge oats", "old fashioned oats"),
    ),
    IngredientMeasure(
        "sunflower-seeds",
        "Sunflower seeds",
        I,
        140,
        Method.poured,
        f"{KING_ARTHUR} (1/4 cup = 35 g)",
        (),
    ),
    IngredientMeasure(
        "pumpkin-seeds",
        "Pumpkin seeds",
        I,
        160,
        Method.poured,
        f"{KING_ARTHUR} (1/4 cup = 40 g)",
        ("pepitas",),
    ),
    IngredientMeasure(
        "sesame-seeds",
        "Sesame seeds",
        I,
        142,
        Method.poured,
        f"{KING_ARTHUR} (1/2 cup = 71 g)",
        (),
    ),
    IngredientMeasure(
        "flaxseed",
        "Flaxseed",
        I,
        140,
        Method.poured,
        f"{KING_ARTHUR} (1/4 cup = 35 g)",
        ("linseed", "flax seed", "flax"),
    ),
    IngredientMeasure(
        "walnuts",
        "Walnuts, chopped",
        I,
        113,
        Method.poured,
        KING_ARTHUR,
        (),
    ),
    IngredientMeasure(
        "raisins",
        "Raisins",
        I,
        149,
        Method.poured,
        f"{KING_ARTHUR} (loose)",
        ("sultanas",),
    ),
    IngredientMeasure(
        "dried-cranberries",
        "Dried cranberries",
        I,
        114,
        Method.poured,
        f"{KING_ARTHUR} (1/2 cup = 57 g)",
        ("cranberries", "craisins"),
    ),
    IngredientMeasure(
        "cocoa-powder",
        "Cocoa powder, unsweetened",
        I,
        84,
        Method.spooned_levelled,
        f"{KING_ARTHUR} (1/2 cup = 42 g)",
        ("cocoa", "cacao powder"),
    ),
)

BY_SLUG: dict[str, IngredientMeasure] = {entry.slug: entry for entry in CATALOGUE}

BY_ALIAS: dict[str, IngredientMeasure] = {
    alias: entry for entry in CATALOGUE for alias in entry.aliases
}

#: Used when nothing matched. Deliberately absent for salt and starter, which
#: must never be guessed — the whole point of §2.1 of the plan.
KIND_DEFAULTS: dict[IngredientKind, str] = {
    IngredientKind.flour: "all-purpose-flour",
    IngredientKind.liquid: "water",
    IngredientKind.inclusion: "rolled-oats",
}


async def seed_measures(session: AsyncSession) -> int:
    """Project the code catalogue into `ingredient_measure`.

    The table is a projection, not a second source of truth: it exists so clients
    can list densities and so `user_ingredient_measure` has a foreign key target.
    Shared by `sdt seed-measurements` and by the test-database setup, because a
    catalogue seeded two slightly different ways is a bug in waiting.
    """
    from sqlalchemy.dialects.postgresql import insert

    from app.models.measurement import IngredientMeasureRow

    for entry in CATALOGUE:
        values = {
            "slug": entry.slug,
            "name": entry.name,
            "kind": entry.kind.value,
            "grams_per_cup": entry.grams_per_cup,
            "method": entry.method.value,
            "source": entry.source,
            "aliases": list(entry.aliases),
            "volume_allowed": entry.volume_allowed,
            "reason": entry.reason,
        }
        await session.execute(
            insert(IngredientMeasureRow)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["slug"],
                set_={k: v for k, v in values.items() if k != "slug"},
            )
        )
    await session.commit()
    return len(CATALOGUE)
