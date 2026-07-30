"""Turning a free-text ingredient name into a density.

`RecipeIngredient.name` is a `String(80)` a baker typed, so "Bread Flour",
"bread flour" and "strong white flour" all have to reach the same row. Matching
is deliberately dumb — normalise, then exact slug, then alias, then a per-kind
default — because a *wrong* match is worse than no match. Fuzzy matching would
turn "rye flour" and "rice flour" into a coin toss.

Overrides arrive as a plain mapping so this module stays pure and testable; the
caller is responsible for loading them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.models.recipe import IngredientKind
from app.services.measurements.catalogue import (
    BY_ALIAS,
    BY_SLUG,
    CATALOGUE,
    KIND_DEFAULTS,
    IngredientMeasure,
)
from app.services.measurements.convert import Basis, Density

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

#: Words that describe handling rather than the ingredient, so they must not
#: prevent a match: "warm water" and "water" are the same density.
NOISE = frozenset(
    {
        "cold",
        "warm",
        "hot",
        "room",
        "temperature",
        "filtered",
        "bottled",
        "organic",
        "fresh",
        "chopped",
        "toasted",
        "raw",
        "whole",
        "ground",
    }
)


def normalise(name: str) -> str:
    """Lowercase, strip punctuation, drop noise words, singularise crudely.

    Crude on purpose. `"Organic Strong White Flour "` and `"strong-white flour"`
    must both become `strong white flour`, and nothing cleverer is needed.
    """
    lowered = _NON_ALNUM.sub(" ", name.strip().lower())
    words = [w for w in lowered.split() if w]
    kept = [w for w in words if w not in NOISE] or words
    singular = [
        w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in kept
    ]
    return " ".join(singular)


def _slug_of(name: str) -> str:
    return normalise(name).replace(" ", "-")


def _lookup(name: str) -> IngredientMeasure | None:
    """Catalogue hit by slug or alias, on the normalised form."""
    normalised = normalise(name)
    slug = normalised.replace(" ", "-")
    if slug in BY_SLUG:
        return BY_SLUG[slug]
    if normalised in BY_ALIAS:
        return BY_ALIAS[normalised]
    # Aliases are authored in natural form; compare normalised on both sides so
    # "sultanas" matches "sultana" and "flax seeds" matches "flax seed".
    for entry in CATALOGUE:
        if normalised in {normalise(alias) for alias in entry.aliases}:
            return entry
        if normalised == normalise(entry.name):
            return entry
    return None


def _refusal(kind: IngredientKind) -> Density:
    """A density that exists only to explain why it will not convert."""
    if kind is IngredientKind.starter:
        return Density(
            slug="starter",
            grams_per_cup=0.0,
            basis=Basis.kind_default,
            volume_allowed=False,
            reason="a levain at peak is mostly gas, so its volume says nothing about "
            "how much of it there is; weigh it",
        )
    return Density(
        slug="salt",
        grams_per_cup=0.0,
        basis=Basis.kind_default,
        volume_allowed=False,
        reason="salt varies 2.25-fold by grind (18 g/tbsp table vs 8 g/tbsp Diamond "
        "Crystal). Name the salt you use, or weigh it.",
    )


def resolve(
    name: str,
    kind: IngredientKind | None = None,
    overrides: Mapping[str, float] | None = None,
) -> Density | None:
    """Find the density for an ingredient name.

    Order: user override, exact slug, alias, kind default. Returns `None` only
    when nothing matched and the kind has no default — for salt and starter the
    result is a `Density` that refuses volume *and says why*, which is far more
    useful to a client than a bare miss.
    """
    entry = _lookup(name)
    slug = entry.slug if entry else _slug_of(name)

    if overrides and slug in overrides:
        # A baker who weighed their own flour outranks any published chart, but
        # not a refusal: no measured density makes a peaked levain measurable.
        if entry is not None and not entry.volume_allowed:
            return _density_from(entry, Basis.catalogue)
        return Density(slug=slug, grams_per_cup=overrides[slug], basis=Basis.user_override)

    if entry is not None:
        return _density_from(entry, Basis.catalogue)

    if kind in (IngredientKind.salt, IngredientKind.starter):
        return _refusal(kind)

    if kind is not None and kind in KIND_DEFAULTS:
        fallback = BY_SLUG[KIND_DEFAULTS[kind]]
        return _density_from(fallback, Basis.kind_default)

    return None


def _density_from(entry: IngredientMeasure, basis: Basis) -> Density:
    return Density(
        slug=entry.slug,
        grams_per_cup=entry.grams_per_cup,
        basis=basis,
        volume_allowed=entry.volume_allowed,
        reason=entry.reason,
    )
