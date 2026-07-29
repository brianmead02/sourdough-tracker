"""Administration, moderation, and account self-service.

Split by who may call it:

* `/admin/*`  — moderator or admin only
* `/account/*` — the signed-in user, acting on their own data

Both live here because they are two halves of the same subject: what an
instance may do with a person's data, and what that person may do about it.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_role
from app.db import get_session
from app.models.bake import Bake
from app.models.recipe import Recipe
from app.models.user import User, UserProfile, UserRole
from app.schemas.admin import (
    AdminUserRow,
    DeleteAccountRequest,
    DeleteAccountResponse,
    InstanceStats,
    ModerationItem,
    SuspendRequest,
)
from app.services import account as account_service
from app.services import auth as auth_service
from app.services import security

SessionDep = Annotated[AsyncSession, Depends(get_session)]

admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(UserRole.moderator))],
)
account_router = APIRouter(prefix="/account", tags=["account"])

DELETE_PHRASE = "DELETE MY ACCOUNT"


# --- moderation -------------------------------------------------------------


@admin_router.get("/users", response_model=list[AdminUserRow])
async def list_users(
    db: SessionDep,
    q: Annotated[str | None, Query(max_length=120)] = None,
    suspended: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AdminUserRow]:
    """Find an account by email or handle."""
    public_recipes = (
        select(func.count())
        .select_from(Recipe)
        .where(
            Recipe.owner_id == User.id,
            Recipe.is_public.is_(True),
            Recipe.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    bakes = (
        select(func.count())
        .select_from(Bake)
        .where(Bake.user_id == User.id, Bake.deleted_at.is_(None))
        .scalar_subquery()
    )

    statement = (
        select(User, UserProfile, public_recipes, bakes)
        .join(UserProfile, UserProfile.user_id == User.id)
        .where(User.deleted_at.is_(None))
    )
    if q:
        pattern = f"%{q.lower()}%"
        statement = statement.where(
            func.lower(User.email).like(pattern) | func.lower(UserProfile.handle).like(pattern)
        )
    if suspended is not None:
        statement = statement.where(User.is_suspended.is_(suspended))

    rows = await db.execute(statement.order_by(User.created_at.desc()).limit(limit).offset(offset))
    return [
        AdminUserRow(
            id=user.id,
            email=user.email,
            handle=profile.handle,
            display_name=profile.display_name,
            role=user.role,
            is_verified=user.is_verified,
            is_suspended=user.is_suspended,
            suspended_reason=user.suspended_reason,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            public_recipes=recipes,
            bakes=bake_count,
        )
        for user, profile, recipes, bake_count in rows.all()
    ]


@admin_router.post("/users/{user_id}/suspend", response_model=AdminUserRow)
async def suspend_user(
    user_id: uuid.UUID, payload: SuspendRequest, actor: CurrentUser, db: SessionDep
) -> AdminUserRow:
    """Suspend an account. Takes effect on the account's very next request."""
    if user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot suspend your own account",
        )

    target = await _live_user(user_id, db)
    if target.role is UserRole.admin:
        # Otherwise one compromised moderator can lock out the operators.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrators cannot be suspended"
        )

    target.is_suspended = True
    target.suspended_reason = payload.reason
    # Cut every live session: suspension is checked per request, but a refresh
    # token would otherwise still mint new access tokens after an unsuspend.
    await auth_service.revoke_all_refresh_tokens(db, target.id)
    await db.flush()
    return await _admin_row(target, db)


@admin_router.post("/users/{user_id}/unsuspend", response_model=AdminUserRow)
async def unsuspend_user(user_id: uuid.UUID, db: SessionDep) -> AdminUserRow:
    target = await _live_user(user_id, db)
    target.is_suspended = False
    target.suspended_reason = None
    await db.flush()
    return await _admin_row(target, db)


@admin_router.get("/moderation/queue", response_model=list[ModerationItem])
async def moderation_queue(
    db: SessionDep,
    order: Annotated[Literal["newest", "most_starred"], Query()] = "newest",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ModerationItem]:
    """Published recipes, newest first — the public surface worth reviewing."""
    ordering = Recipe.star_count.desc() if order == "most_starred" else Recipe.created_at.desc()
    rows = await db.execute(
        select(Recipe, UserProfile.handle, User.is_suspended)
        .join(User, User.id == Recipe.owner_id)
        .join(UserProfile, UserProfile.user_id == Recipe.owner_id)
        .where(Recipe.is_public.is_(True), Recipe.deleted_at.is_(None))
        .order_by(ordering)
        .limit(limit)
    )
    return [
        ModerationItem(
            recipe_id=recipe.id,
            name=recipe.name,
            description=recipe.description,
            owner_id=recipe.owner_id,
            owner_handle=handle,
            owner_suspended=is_suspended,
            tags=recipe.tags,
            star_count=recipe.star_count,
            fork_count=recipe.fork_count,
            created_at=recipe.created_at,
        )
        for recipe, handle, is_suspended in rows.all()
    ]


@admin_router.post("/recipes/{recipe_id}/unpublish", status_code=status.HTTP_204_NO_CONTENT)
async def unpublish_recipe(recipe_id: uuid.UUID, db: SessionDep) -> None:
    """Withdraw a recipe from public view without destroying the author's copy.

    Deliberately not a delete: moderation should be reversible, and taking
    someone's own work away from them is a bigger act than hiding it.
    """
    recipe = await db.get(Recipe, recipe_id)
    if recipe is None or recipe.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    recipe.is_public = False
    await db.flush()


@admin_router.get("/stats", response_model=InstanceStats)
async def stats(db: SessionDep) -> InstanceStats:
    return InstanceStats(**await account_service.instance_stats(db))


async def _live_user(user_id: uuid.UUID, db: AsyncSession) -> User:
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def _admin_row(user: User, db: AsyncSession) -> AdminUserRow:
    profile = await db.get(UserProfile, user.id)
    return AdminUserRow(
        id=user.id,
        email=user.email,
        handle=profile.handle if profile else "",
        display_name=profile.display_name if profile else "",
        role=user.role,
        is_verified=user.is_verified,
        is_suspended=user.is_suspended,
        suspended_reason=user.suspended_reason,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        public_recipes=0,
        bakes=0,
    )


# --- account self-service ---------------------------------------------------


@account_router.get("/export")
async def export_my_data(user: CurrentUser, db: SessionDep) -> Response:
    """Download everything this account holds, as JSON.

    Served as an attachment rather than a rendered response: it is a file the
    user keeps, not a page they read. Credentials — password hash, token
    hashes — are excluded; they are secrets, not personal data.
    """
    import json

    payload: dict[str, Any] = await account_service.export_account(db, user)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        content=json.dumps(payload, indent=2, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="sourdough-export-{user.profile.handle}-{stamp}.json"'
            )
        },
    )


@account_router.post("/delete", response_model=DeleteAccountResponse)
async def delete_my_account(
    payload: DeleteAccountRequest, user: CurrentUser, db: SessionDep
) -> DeleteAccountResponse:
    """Erase this account permanently.

    Requires the current password *and* a typed confirmation phrase. This is not
    recoverable and there is no grace period, so it should be hard to do by
    accident and impossible to do by CSRF.
    """
    if payload.confirm != DELETE_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f'Type exactly "{DELETE_PHRASE}" to confirm',
        )
    if not security.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password is incorrect")

    removed, photos = await account_service.delete_account(db, user)
    return DeleteAccountResponse(deleted=True, rows_removed=removed, photos_removed=photos)
