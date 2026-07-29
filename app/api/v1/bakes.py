"""Bakes: the log of what was actually made, with ratings and photos."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, VerifiedUser
from app.db import get_session
from app.models.bake import Bake, BakePhoto, BakeRating, BakeStatus
from app.models.proofing import ProofSession
from app.models.recipe import Recipe
from app.schemas.bake import (
    BakeCompleteRequest,
    BakeCreate,
    BakeResponse,
    BakeUpdate,
    PhotoAttach,
    PhotoResponse,
    RatingInput,
    RatingResponse,
)
from app.schemas.proofing import ProofSessionResponse
from app.services import storage
from app.services.starters import CLOCK_SKEW_ALLOWANCE, MAX_BACKDATE

router = APIRouter(prefix="/bakes", tags=["bakes"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

MAX_PHOTOS_PER_BAKE = 20


def _to_response(bake: Bake) -> BakeResponse:
    return BakeResponse(
        **{
            field: getattr(bake, field)
            for field in BakeResponse.model_fields
            if field not in {"rating", "photo_count"}
        },
        rating=RatingResponse.model_validate(bake.rating) if bake.rating else None,
        photo_count=len(bake.photos),
    )


def _validate_timestamp(value: datetime, now: datetime, field: str) -> None:
    if value > now + CLOCK_SKEW_ALLOWANCE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} cannot be in the future",
        )
    if value < now - MAX_BACKDATE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field} cannot be more than {MAX_BACKDATE.days} days in the past",
        )


async def _get_owned(bake_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Bake:
    result = await db.execute(
        select(Bake).where(Bake.id == bake_id, Bake.user_id == user_id, Bake.deleted_at.is_(None))
    )
    bake = result.scalar_one_or_none()
    if bake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bake not found")
    return bake


# --- CRUD -------------------------------------------------------------------


@router.post("", response_model=BakeResponse, status_code=status.HTTP_201_CREATED)
async def create_bake(payload: BakeCreate, user: VerifiedUser, db: SessionDep) -> BakeResponse:
    now = datetime.now(UTC)
    started_at = payload.started_at or now
    _validate_timestamp(started_at, now, "started_at")

    if payload.recipe_id is not None:
        readable = await db.execute(
            select(Recipe.id).where(
                Recipe.id == payload.recipe_id,
                Recipe.deleted_at.is_(None),
                or_(Recipe.owner_id == user.id, Recipe.is_public.is_(True)),
            )
        )
        if readable.first() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")

    bake = Bake(
        user_id=user.id,
        started_at=started_at,
        **payload.model_dump(exclude={"started_at"}),
    )
    db.add(bake)
    await db.flush()
    # A newly inserted row has no loaded relationships. `selectin` only applies
    # to rows fetched by a query, so touching bake.rating/.photos here would be
    # a lazy load inside async context (MissingGreenlet).
    await db.refresh(bake, attribute_names=["rating", "photos"])
    return _to_response(bake)


@router.get("", response_model=list[BakeResponse])
async def list_bakes(
    user: CurrentUser,
    db: SessionDep,
    bake_status: Annotated[BakeStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BakeResponse]:
    conditions = [Bake.user_id == user.id, Bake.deleted_at.is_(None)]
    if bake_status is not None:
        conditions.append(Bake.status == bake_status)

    result = await db.execute(
        select(Bake).where(*conditions).order_by(Bake.started_at.desc()).limit(limit).offset(offset)
    )
    return [_to_response(b) for b in result.scalars().all()]


@router.get("/{bake_id}", response_model=BakeResponse)
async def get_bake(bake_id: uuid.UUID, user: CurrentUser, db: SessionDep) -> BakeResponse:
    return _to_response(await _get_owned(bake_id, user.id, db))


@router.patch("/{bake_id}", response_model=BakeResponse)
async def update_bake(
    bake_id: uuid.UUID, payload: BakeUpdate, user: VerifiedUser, db: SessionDep
) -> BakeResponse:
    bake = await _get_owned(bake_id, user.id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(bake, field, value)
    await db.flush()
    return _to_response(bake)


@router.delete("/{bake_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bake(bake_id: uuid.UUID, user: VerifiedUser, db: SessionDep) -> None:
    bake = await _get_owned(bake_id, user.id, db)
    bake.deleted_at = datetime.now(UTC)


@router.post("/{bake_id}/complete", response_model=BakeResponse)
async def complete_bake(
    bake_id: uuid.UUID, payload: BakeCompleteRequest, user: VerifiedUser, db: SessionDep
) -> BakeResponse:
    bake = await _get_owned(bake_id, user.id, db)
    if bake.status is not BakeStatus.in_progress:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This bake is already {bake.status.value}",
        )

    now = datetime.now(UTC)
    finished_at = payload.finished_at or now
    _validate_timestamp(finished_at, now, "finished_at")
    if finished_at < bake.started_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="finished_at cannot be before the bake started",
        )

    bake.status = BakeStatus.done
    bake.finished_at = finished_at
    for field in ("oven_temp_c", "bake_time_minutes", "notes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(bake, field, value)

    await db.flush()
    return _to_response(bake)


# --- rating -----------------------------------------------------------------


@router.put("/{bake_id}/rating", response_model=RatingResponse)
async def rate_bake(
    bake_id: uuid.UUID, payload: RatingInput, user: VerifiedUser, db: SessionDep
) -> RatingResponse:
    """Upsert — a bake has at most one rating, and bakers revise their opinion."""
    bake = await _get_owned(bake_id, user.id, db)

    if bake.rating is None:
        bake.rating = BakeRating(**payload.model_dump())
    else:
        for field, value in payload.model_dump().items():
            setattr(bake.rating, field, value)

    await db.flush()
    return RatingResponse.model_validate(bake.rating)


@router.delete("/{bake_id}/rating", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rating(bake_id: uuid.UUID, user: VerifiedUser, db: SessionDep) -> None:
    bake = await _get_owned(bake_id, user.id, db)
    bake.rating = None
    await db.flush()


# --- photos -----------------------------------------------------------------


@router.post("/{bake_id}/photos", response_model=PhotoResponse, status_code=status.HTTP_201_CREATED)
async def attach_photo(
    bake_id: uuid.UUID, payload: PhotoAttach, user: VerifiedUser, db: SessionDep
) -> PhotoResponse:
    """Attach an already-uploaded object to a bake.

    The key must be one this user was granted (the owner id is embedded in it)
    and the object must actually exist — otherwise a client could attach someone
    else's photo, or a key for an upload that never happened.
    """
    bake = await _get_owned(bake_id, user.id, db)

    if len(bake.photos) >= MAX_PHOTOS_PER_BAKE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A bake may have at most {MAX_PHOTOS_PER_BAKE} photos",
        )

    if storage.key_owner(payload.object_key) != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    info = await storage.head(payload.object_key)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    photo = BakePhoto(bake_id=bake.id, size_bytes=info.size_bytes, **payload.model_dump())
    db.add(photo)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That upload is already attached to a bake",
        ) from exc

    return PhotoResponse(
        **{f: getattr(photo, f) for f in PhotoResponse.model_fields if f != "url"},
        url=storage.presign_download(photo.object_key),
    )


@router.get("/{bake_id}/photos", response_model=list[PhotoResponse])
async def list_photos(bake_id: uuid.UUID, user: CurrentUser, db: SessionDep) -> list[PhotoResponse]:
    bake = await _get_owned(bake_id, user.id, db)
    return [
        PhotoResponse(
            **{f: getattr(photo, f) for f in PhotoResponse.model_fields if f != "url"},
            url=storage.presign_download(photo.object_key),
        )
        for photo in bake.photos
    ]


@router.delete("/{bake_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    bake_id: uuid.UUID, photo_id: uuid.UUID, user: VerifiedUser, db: SessionDep
) -> None:
    bake = await _get_owned(bake_id, user.id, db)
    photo = next((p for p in bake.photos if p.id == photo_id), None)
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    object_key = photo.object_key
    bake.photos.remove(photo)
    await db.flush()
    # Best-effort: a stranded object costs storage, a failed request costs the user.
    await storage.delete(object_key)


# --- linked proof sessions --------------------------------------------------


@router.get("/{bake_id}/proof-sessions", response_model=list[ProofSessionResponse])
async def bake_proof_sessions(
    bake_id: uuid.UUID, user: CurrentUser, db: SessionDep
) -> list[ProofSessionResponse]:
    bake = await _get_owned(bake_id, user.id, db)
    result = await db.execute(
        select(ProofSession)
        .where(ProofSession.bake_id == bake.id)
        .order_by(ProofSession.started_at)
    )
    return [ProofSessionResponse.model_validate(s) for s in result.scalars().all()]
