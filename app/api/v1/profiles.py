"""Public profile reads and self-service profile edits."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.db import get_session
from app.models.user import User, UserProfile
from app.schemas.user import OwnProfile, ProfileUpdate, PublicProfile

router = APIRouter(prefix="/profiles", tags=["profiles"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/me", response_model=OwnProfile)
async def read_own_profile(user: CurrentUser) -> OwnProfile:
    return OwnProfile.model_validate(user.profile)


@router.patch("/me", response_model=OwnProfile)
async def update_own_profile(
    payload: ProfileUpdate, user: CurrentUser, session: SessionDep
) -> OwnProfile:
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user.profile, field, value)
    await session.flush()
    return OwnProfile.model_validate(user.profile)


@router.get("/{handle}", response_model=PublicProfile)
async def read_public_profile(handle: str, session: SessionDep) -> PublicProfile:
    """A private profile is indistinguishable from a missing one — publishing is opt-in."""
    result = await session.execute(
        select(UserProfile)
        .join(User, User.id == UserProfile.user_id)
        .where(
            UserProfile.handle == handle.lower(),
            UserProfile.is_public.is_(True),
            User.deleted_at.is_(None),
            User.is_suspended.is_(False),
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return PublicProfile.model_validate(profile)
