"""Recipes: CRUD, public browsing, scaling, forking and stars."""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, VerifiedUser
from app.db import get_session
from app.models.recipe import Recipe, RecipeIngredient, RecipeStar
from app.models.user import User, UserProfile
from app.schemas.recipe import (
    IngredientInput,
    PublicRecipeSummary,
    RecipeCreate,
    RecipeResponse,
    RecipeUpdate,
    ScaledRecipeResponse,
)
from app.services import recipes as recipe_service

router = APIRouter(prefix="/recipes", tags=["recipes"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _to_ingredients(recipe: Recipe) -> list[recipe_service.Ingredient]:
    return [recipe_service.Ingredient(i.name, i.kind, i.percentage) for i in recipe.ingredients]


def _replace_ingredients(recipe: Recipe, payload: list[IngredientInput]) -> None:
    recipe.ingredients = [
        RecipeIngredient(
            name=item.name, kind=item.kind, percentage=item.percentage, sort_order=index
        )
        for index, item in enumerate(payload)
    ]


async def _get_owned(recipe_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Recipe:
    result = await db.execute(
        select(Recipe).where(
            Recipe.id == recipe_id, Recipe.owner_id == user_id, Recipe.deleted_at.is_(None)
        )
    )
    recipe = result.scalar_one_or_none()
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    return recipe


async def _get_readable(recipe_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Recipe:
    """Own recipe, or someone else's published one."""
    result = await db.execute(
        select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.deleted_at.is_(None),
            or_(Recipe.owner_id == user_id, Recipe.is_public.is_(True)),
        )
    )
    recipe = result.scalar_one_or_none()
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    return recipe


# --- CRUD -------------------------------------------------------------------


@router.post("", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    payload: RecipeCreate, user: VerifiedUser, db: SessionDep
) -> RecipeResponse:
    recipe = Recipe(owner_id=user.id, **payload.model_dump(exclude={"ingredients"}))
    _replace_ingredients(recipe, payload.ingredients)
    db.add(recipe)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a recipe with that name",
        ) from exc
    return RecipeResponse.model_validate(recipe)


@router.get("", response_model=list[RecipeResponse])
async def list_my_recipes(
    user: CurrentUser,
    db: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RecipeResponse]:
    result = await db.execute(
        select(Recipe)
        .where(Recipe.owner_id == user.id, Recipe.deleted_at.is_(None))
        .order_by(Recipe.name)
        .limit(limit)
        .offset(offset)
    )
    return [RecipeResponse.model_validate(r) for r in result.scalars().all()]


@router.get("/public", response_model=list[PublicRecipeSummary])
async def browse_public_recipes(
    db: SessionDep,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=80)] = None,
    tag: Annotated[str | None, Query(max_length=30)] = None,
    sort: Annotated[Literal["stars", "recent", "forks"], Query()] = "stars",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PublicRecipeSummary]:
    """Published recipes from every user. Suspended accounts are excluded."""
    statement = (
        select(Recipe, UserProfile.handle)
        .join(User, User.id == Recipe.owner_id)
        .join(UserProfile, UserProfile.user_id == Recipe.owner_id)
        .where(
            Recipe.is_public.is_(True),
            Recipe.deleted_at.is_(None),
            User.deleted_at.is_(None),
            User.is_suspended.is_(False),
        )
    )

    if q:
        pattern = f"%{q.lower()}%"
        statement = statement.where(
            or_(func.lower(Recipe.name).like(pattern), func.lower(Recipe.description).like(pattern))
        )
    if tag:
        statement = statement.where(Recipe.tags.contains([tag.lower()]))

    orders: dict[str, Any] = {
        "stars": Recipe.star_count.desc(),
        "forks": Recipe.fork_count.desc(),
        "recent": Recipe.created_at.desc(),
    }
    statement = (
        statement.order_by(orders[sort], Recipe.created_at.desc()).limit(limit).offset(offset)
    )

    rows = await db.execute(statement)
    return [
        PublicRecipeSummary(
            id=recipe.id,
            name=recipe.name,
            description=recipe.description,
            owner_handle=handle,
            tags=recipe.tags,
            star_count=recipe.star_count,
            fork_count=recipe.fork_count,
            created_at=recipe.created_at,
        )
        for recipe, handle in rows.all()
    ]


@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(recipe_id: uuid.UUID, user: CurrentUser, db: SessionDep) -> RecipeResponse:
    recipe = await _get_readable(recipe_id, user.id, db)
    return RecipeResponse.model_validate(recipe)


@router.patch("/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(
    recipe_id: uuid.UUID, payload: RecipeUpdate, user: VerifiedUser, db: SessionDep
) -> RecipeResponse:
    recipe = await _get_owned(recipe_id, user.id, db)
    changes = payload.model_dump(exclude_unset=True, exclude={"ingredients"})
    for field, value in changes.items():
        setattr(recipe, field, value)

    if payload.ingredients is not None:
        _replace_ingredients(recipe, payload.ingredients)
        # Version bumps only when the formula changes, so a fork can tell
        # whether the parent has moved on.
        recipe.version += 1

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a recipe with that name",
        ) from exc
    return RecipeResponse.model_validate(recipe)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(recipe_id: uuid.UUID, user: VerifiedUser, db: SessionDep) -> None:
    recipe = await _get_owned(recipe_id, user.id, db)
    recipe.deleted_at = datetime.now(UTC)
    # Withdraw it from the public listing immediately; forks already made keep working.
    recipe.is_public = False


# --- scaling ----------------------------------------------------------------


@router.get("/{recipe_id}/scale", response_model=ScaledRecipeResponse)
async def scale_recipe(
    recipe_id: uuid.UUID,
    user: CurrentUser,
    db: SessionDep,
    dough_weight_g: Annotated[float | None, Query(gt=0, le=100_000)] = None,
    flour_g: Annotated[float | None, Query(gt=0, le=100_000)] = None,
    loaf_count: Annotated[int, Query(ge=1, le=100)] = 1,
) -> ScaledRecipeResponse:
    """Resolve the percentages into grams. Defaults to the recipe's own batch size."""
    recipe = await _get_readable(recipe_id, user.id, db)

    if dough_weight_g is None and flour_g is None:
        dough_weight_g = recipe.default_dough_weight_g

    try:
        scaled = recipe_service.scale(
            _to_ingredients(recipe),
            starter_hydration_pct=recipe.starter_hydration_pct,
            dough_weight_g=dough_weight_g,
            flour_g=flour_g,
            loaf_count=loaf_count,
        )
    except recipe_service.RecipeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    return ScaledRecipeResponse(**asdict(scaled))


# --- forking and stars ------------------------------------------------------


@router.post(
    "/{recipe_id}/fork", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED
)
async def fork_recipe(recipe_id: uuid.UUID, user: VerifiedUser, db: SessionDep) -> RecipeResponse:
    """Copy a readable recipe into your own collection.

    The copy is private and starts at version 1: it is a new recipe that
    remembers its parent, not a live link to it.
    """
    source = await _get_readable(recipe_id, user.id, db)

    name = source.name
    existing = await db.execute(
        select(Recipe.id).where(
            Recipe.owner_id == user.id, Recipe.name == name, Recipe.deleted_at.is_(None)
        )
    )
    if existing.first() is not None:
        name = f"{source.name} (fork)"[:120]

    fork = Recipe(
        owner_id=user.id,
        name=name,
        description=source.description,
        is_public=False,
        forked_from_id=source.id,
        default_dough_weight_g=source.default_dough_weight_g,
        starter_hydration_pct=source.starter_hydration_pct,
        tags=list(source.tags),
        steps=list(source.steps),
    )
    fork.ingredients = [
        RecipeIngredient(name=i.name, kind=i.kind, percentage=i.percentage, sort_order=i.sort_order)
        for i in source.ingredients
    ]
    db.add(fork)

    if source.owner_id != user.id:
        source.fork_count += 1

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a recipe with that name",
        ) from exc
    return RecipeResponse.model_validate(fork)


@router.post("/{recipe_id}/star", status_code=status.HTTP_204_NO_CONTENT)
async def star_recipe(
    recipe_id: uuid.UUID, user: VerifiedUser, db: SessionDep, response: Response
) -> None:
    recipe = await _get_readable(recipe_id, user.id, db)
    if recipe.owner_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You cannot star your own recipe"
        )

    already = await db.execute(
        select(RecipeStar).where(RecipeStar.user_id == user.id, RecipeStar.recipe_id == recipe.id)
    )
    if already.scalar_one_or_none() is not None:
        return  # idempotent

    db.add(RecipeStar(user_id=user.id, recipe_id=recipe.id))
    recipe.star_count += 1
    await db.flush()


@router.delete("/{recipe_id}/star", status_code=status.HTTP_204_NO_CONTENT)
async def unstar_recipe(recipe_id: uuid.UUID, user: VerifiedUser, db: SessionDep) -> None:
    result = await db.execute(
        delete(RecipeStar)
        .where(RecipeStar.user_id == user.id, RecipeStar.recipe_id == recipe_id)
        .returning(RecipeStar.recipe_id)
    )
    if result.first() is None:
        return  # idempotent

    recipe = await db.get(Recipe, recipe_id)
    if recipe is not None and recipe.star_count > 0:
        recipe.star_count -= 1
