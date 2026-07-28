"""Starter management: CRUD, feeding log, observations, schedule and streaks."""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, VerifiedUser
from app.db import get_session
from app.models.starter import Feeding, Starter, StarterObservation, StarterState
from app.schemas.starter import (
    FeedingCreate,
    FeedingResponse,
    ObservationCreate,
    ObservationResponse,
    ScheduleItem,
    StarterCreate,
    StarterListItem,
    StarterResponse,
    StarterUpdate,
    StreakResponse,
    SuggestedFeedResponse,
    SuggestFeedRequest,
)
from app.services import starters as starter_service

router = APIRouter(prefix="/starters", tags=["starters"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# States that are actively on a feeding schedule.
SCHEDULED_STATES = (StarterState.active, StarterState.fridge)


async def _get_owned_starter(
    starter_id: uuid.UUID, user_id: uuid.UUID, session: AsyncSession
) -> Starter:
    """404 rather than 403 for someone else's starter — existence is not disclosed."""
    result = await session.execute(
        select(Starter).where(
            Starter.id == starter_id,
            Starter.user_id == user_id,
            Starter.deleted_at.is_(None),
        )
    )
    starter = result.scalar_one_or_none()
    if starter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Starter not found")
    return starter


async def _last_fed_map(
    session: AsyncSession, starter_ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """Most recent feeding per starter, in one aggregate rather than N queries."""
    if not starter_ids:
        return {}
    result = await session.execute(
        select(Feeding.starter_id, func.max(Feeding.fed_at))
        .where(Feeding.starter_id.in_(starter_ids))
        .group_by(Feeding.starter_id)
    )
    return {row[0]: row[1] for row in result.all()}


# --- starters ---------------------------------------------------------------


@router.post("", response_model=StarterResponse, status_code=status.HTTP_201_CREATED)
async def create_starter(
    payload: StarterCreate, user: VerifiedUser, session: SessionDep
) -> StarterResponse:
    starter = Starter(user_id=user.id, **payload.model_dump())
    session.add(starter)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a starter with that name",
        ) from exc
    return StarterResponse.model_validate(starter)


@router.get("", response_model=list[StarterListItem])
async def list_starters(
    user: CurrentUser,
    session: SessionDep,
    include_retired: Annotated[bool, Query()] = False,
) -> list[StarterListItem]:
    conditions = [Starter.user_id == user.id, Starter.deleted_at.is_(None)]
    if not include_retired:
        conditions.append(Starter.state != StarterState.retired)

    result = await session.execute(select(Starter).where(*conditions).order_by(Starter.name))
    starters = list(result.scalars().all())
    last_fed = await _last_fed_map(session, [s.id for s in starters])
    now = datetime.now(UTC)

    items: list[StarterListItem] = []
    for starter in starters:
        entry = starter_service.compute_schedule(
            last_fed.get(starter.id),
            starter.feed_interval_hours,
            now,
            on_schedule=starter.state in SCHEDULED_STATES,
        )
        items.append(
            StarterListItem(
                **StarterResponse.model_validate(starter).model_dump(),
                status=entry.status,
                last_fed_at=entry.last_fed_at,
                next_due_at=entry.next_due_at,
                hours_until_due=entry.hours_until_due,
            )
        )
    return items


@router.get("/schedule", response_model=list[ScheduleItem])
async def feeding_schedule(user: CurrentUser, session: SessionDep) -> list[ScheduleItem]:
    """Everything on a schedule, most urgent first."""
    result = await session.execute(
        select(Starter).where(
            Starter.user_id == user.id,
            Starter.deleted_at.is_(None),
            Starter.state.in_(SCHEDULED_STATES),
        )
    )
    starters = list(result.scalars().all())
    last_fed = await _last_fed_map(session, [s.id for s in starters])
    now = datetime.now(UTC)

    items = [
        ScheduleItem(
            starter_id=starter.id,
            name=starter.name,
            state=starter.state,
            feed_interval_hours=starter.feed_interval_hours,
            **asdict(
                starter_service.compute_schedule(
                    last_fed.get(starter.id), starter.feed_interval_hours, now
                )
            ),
        )
        for starter in starters
    ]
    # Never-fed starters sort first; they need attention most.
    return sorted(
        items,
        key=lambda i: (i.hours_until_due is not None, i.hours_until_due or 0.0),
    )


@router.get("/{starter_id}", response_model=StarterResponse)
async def get_starter(
    starter_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> StarterResponse:
    starter = await _get_owned_starter(starter_id, user.id, session)
    return StarterResponse.model_validate(starter)


@router.patch("/{starter_id}", response_model=StarterResponse)
async def update_starter(
    starter_id: uuid.UUID, payload: StarterUpdate, user: VerifiedUser, session: SessionDep
) -> StarterResponse:
    starter = await _get_owned_starter(starter_id, user.id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(starter, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a starter with that name",
        ) from exc
    return StarterResponse.model_validate(starter)


@router.delete("/{starter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_starter(starter_id: uuid.UUID, user: VerifiedUser, session: SessionDep) -> None:
    """Soft delete — the feeding history stays, so XP and achievements cannot be
    farmed by deleting and recreating (docs/PLAN.md §7)."""
    starter = await _get_owned_starter(starter_id, user.id, session)
    starter.deleted_at = datetime.now(UTC)


# --- feedings ---------------------------------------------------------------


@router.post(
    "/{starter_id}/feedings", response_model=FeedingResponse, status_code=status.HTTP_201_CREATED
)
async def log_feeding(
    starter_id: uuid.UUID, payload: FeedingCreate, user: VerifiedUser, session: SessionDep
) -> FeedingResponse:
    starter = await _get_owned_starter(starter_id, user.id, session)
    now = datetime.now(UTC)
    fed_at = payload.fed_at or now

    try:
        starter_service.validate_fed_at(fed_at, now)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    # Reject near-duplicates rather than silently discounting them: a user who
    # double-taps should be told, not quietly ignored.
    window = starter_service.MIN_FEEDING_GAP
    clash = await session.execute(
        select(Feeding.id).where(
            Feeding.starter_id == starter.id,
            Feeding.fed_at > fed_at - window,
            Feeding.fed_at < fed_at + window,
        )
    )
    if clash.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A feeding is already recorded within "
                f"{int(window.total_seconds() // 60)} minutes of that time"
            ),
        )

    feeding = Feeding(
        starter_id=starter.id, **payload.model_dump(exclude={"fed_at"}), fed_at=fed_at
    )
    session.add(feeding)
    await session.flush()
    return FeedingResponse.model_validate(feeding)


@router.get("/{starter_id}/feedings", response_model=list[FeedingResponse])
async def list_feedings(
    starter_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FeedingResponse]:
    starter = await _get_owned_starter(starter_id, user.id, session)
    result = await session.execute(
        select(Feeding)
        .where(Feeding.starter_id == starter.id)
        .order_by(Feeding.fed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [FeedingResponse.model_validate(f) for f in result.scalars().all()]


# --- observations -----------------------------------------------------------


@router.post(
    "/{starter_id}/observations",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def log_observation(
    starter_id: uuid.UUID, payload: ObservationCreate, user: VerifiedUser, session: SessionDep
) -> ObservationResponse:
    starter = await _get_owned_starter(starter_id, user.id, session)
    now = datetime.now(UTC)
    observed_at = payload.observed_at or now

    try:
        starter_service.validate_fed_at(observed_at, now)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc).replace("fed_at", "observed_at"),
        ) from exc

    if payload.feeding_id is not None:
        owns_feeding = await session.execute(
            select(Feeding.id).where(
                Feeding.id == payload.feeding_id, Feeding.starter_id == starter.id
            )
        )
        if owns_feeding.first() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="feeding_id does not belong to this starter",
            )

    observation = StarterObservation(
        starter_id=starter.id,
        **payload.model_dump(exclude={"observed_at"}),
        observed_at=observed_at,
    )
    session.add(observation)
    await session.flush()
    return ObservationResponse.model_validate(observation)


@router.get("/{starter_id}/observations", response_model=list[ObservationResponse])
async def list_observations(
    starter_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ObservationResponse]:
    starter = await _get_owned_starter(starter_id, user.id, session)
    result = await session.execute(
        select(StarterObservation)
        .where(StarterObservation.starter_id == starter.id)
        .order_by(StarterObservation.observed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [ObservationResponse.model_validate(o) for o in result.scalars().all()]


# --- derived views ----------------------------------------------------------


@router.get("/{starter_id}/streak", response_model=StreakResponse)
async def get_streak(
    starter_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> StreakResponse:
    starter = await _get_owned_starter(starter_id, user.id, session)
    result = await session.execute(
        select(Feeding.fed_at).where(Feeding.starter_id == starter.id).order_by(Feeding.fed_at)
    )
    stats = starter_service.compute_streak(
        list(result.scalars().all()), starter.feed_interval_hours, datetime.now(UTC)
    )
    return StreakResponse(starter_id=starter.id, **asdict(stats))


@router.post("/{starter_id}/suggested-feed", response_model=SuggestedFeedResponse)
async def suggested_feed(
    starter_id: uuid.UUID, payload: SuggestFeedRequest, user: CurrentUser, session: SessionDep
) -> SuggestedFeedResponse:
    starter = await _get_owned_starter(starter_id, user.id, session)
    suggestion = starter_service.suggest_feed(
        starter.ratio_starter,
        starter.ratio_flour,
        starter.ratio_water,
        starter_g=payload.starter_g,
        total_g=payload.total_g,
    )
    return SuggestedFeedResponse(**asdict(suggestion))
