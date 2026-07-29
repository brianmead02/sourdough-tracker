"""Proof sessions: start, check in, complete, and live ETAs."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, VerifiedUser
from app.db import get_session
from app.models.bake import Bake
from app.models.proofing import ProofCheck, ProofSession, ProofStatus
from app.models.starter import Starter
from app.schemas.proofing import (
    ActiveProofSession,
    EstimateRequest,
    EstimateResponse,
    ProofCheckCreate,
    ProofCheckResponse,
    ProofCompleteRequest,
    ProofSessionCreate,
    ProofSessionResponse,
)
from app.services import fermentation
from app.services import proofing as proof_service
from app.services.starters import CLOCK_SKEW_ALLOWANCE, MAX_BACKDATE

router = APIRouter(prefix="/proofing", tags=["proofing"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _get_owned_session(
    session_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> ProofSession:
    result = await db.execute(
        select(ProofSession).where(ProofSession.id == session_id, ProofSession.user_id == user_id)
    )
    proof = result.scalar_one_or_none()
    if proof is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proof session not found")
    return proof


def _require_running(proof: ProofSession) -> None:
    if proof.status is not ProofStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This proof session is already {proof.status.value}",
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


# --- estimate ---------------------------------------------------------------


@router.post("/estimate", response_model=EstimateResponse)
async def estimate(payload: EstimateRequest, user: CurrentUser) -> EstimateResponse:
    """Preview how long a proof would take, without starting one."""
    coeffs = fermentation.coefficients()
    assert payload.target_rise_pct is not None  # set by the schema validator

    if payload.target_rise_pct <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This stage is time-based and has no rise to estimate",
        )

    hours = fermentation.predict_duration_hours(
        payload.target_rise_pct,
        payload.dough_temp_c,
        payload.starter_pct,
        payload.vigour,
        coeffs,
    )
    low, high = fermentation.confidence_window(hours, 0, coeffs)
    rate = fermentation.predict_rate(
        payload.dough_temp_c, payload.starter_pct, payload.vigour, coeffs
    )
    return EstimateResponse(
        hours=round(hours, 2),
        earliest_hours=round(low, 2),
        latest_hours=round(high, 2),
        rise_per_hour_pct=round(rate * 100, 2),
    )


# --- sessions ---------------------------------------------------------------


@router.post("/sessions", response_model=ProofSessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: ProofSessionCreate, user: VerifiedUser, db: SessionDep
) -> ProofSessionResponse:
    now = datetime.now(UTC)
    started_at = payload.started_at or now
    _validate_timestamp(started_at, now, "started_at")

    if payload.starter_id is not None:
        owned = await db.execute(
            select(Starter.id).where(
                Starter.id == payload.starter_id,
                Starter.user_id == user.id,
                Starter.deleted_at.is_(None),
            )
        )
        if owned.first() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Starter not found")

    if payload.bake_id is not None:
        owned_bake = await db.execute(
            select(Bake.id).where(
                Bake.id == payload.bake_id,
                Bake.user_id == user.id,
                Bake.deleted_at.is_(None),
            )
        )
        if owned_bake.first() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bake not found")

    coeffs = fermentation.coefficients()
    vigour = await proof_service.estimate_starter_vigour(db, payload.starter_id, coeffs)
    assert payload.target_rise_pct is not None

    prediction = proof_service.predict_from_start(
        started_at=started_at,
        target_rise_pct=payload.target_rise_pct,
        planned_duration_minutes=payload.planned_duration_minutes,
        dough_temp_c=payload.dough_temp_c,
        starter_pct=payload.starter_pct,
        vigour=vigour,
        c=coeffs,
    )

    proof = ProofSession(
        user_id=user.id,
        started_at=started_at,
        vigour_used=vigour,
        predicted_end_at=prediction.predicted_end_at,
        window_start_at=prediction.window_start_at,
        window_end_at=prediction.window_end_at,
        **payload.model_dump(exclude={"started_at"}),
    )
    db.add(proof)
    await db.flush()
    return ProofSessionResponse.model_validate(proof)


@router.get("/sessions", response_model=list[ProofSessionResponse])
async def list_sessions(
    user: CurrentUser,
    db: SessionDep,
    session_status: Annotated[ProofStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProofSessionResponse]:
    conditions = [ProofSession.user_id == user.id]
    if session_status is not None:
        conditions.append(ProofSession.status == session_status)

    result = await db.execute(
        select(ProofSession)
        .where(*conditions)
        .order_by(ProofSession.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [ProofSessionResponse.model_validate(p) for p in result.scalars().all()]


@router.get("/sessions/active", response_model=list[ActiveProofSession])
async def active_sessions(user: CurrentUser, db: SessionDep) -> list[ActiveProofSession]:
    """Everything currently proofing, with the numbers a countdown needs."""
    result = await db.execute(
        select(ProofSession)
        .where(ProofSession.user_id == user.id, ProofSession.status == ProofStatus.running)
        .order_by(ProofSession.predicted_end_at)
    )
    sessions = list(result.scalars().all())
    if not sessions:
        return []

    ids = [s.id for s in sessions]
    count_rows = await db.execute(
        select(ProofCheck.session_id, func.count())
        .where(ProofCheck.session_id.in_(ids))
        .group_by(ProofCheck.session_id)
    )
    counts: dict[uuid.UUID, int] = {row[0]: row[1] for row in count_rows.all()}

    # Most recent rise reading per session, via the row with the greatest checked_at.
    latest_rise: dict[uuid.UUID, float] = {}
    newest = (
        select(ProofCheck.session_id, func.max(ProofCheck.checked_at).label("checked_at"))
        .where(ProofCheck.session_id.in_(ids))
        .group_by(ProofCheck.session_id)
        .subquery()
    )
    rows = await db.execute(
        select(ProofCheck.session_id, ProofCheck.rise_pct).join(
            newest,
            (ProofCheck.session_id == newest.c.session_id)
            & (ProofCheck.checked_at == newest.c.checked_at),
        )
    )
    for session_id, rise_pct in rows.all():
        latest_rise[session_id] = rise_pct

    now = datetime.now(UTC)
    return [
        ActiveProofSession(
            **ProofSessionResponse.model_validate(proof).model_dump(),
            check_count=counts.get(proof.id, 0),
            latest_rise_pct=latest_rise.get(proof.id),
            progress_pct=proof_service.progress_pct(proof, latest_rise.get(proof.id), now),
            hours_remaining=round((proof.predicted_end_at - now).total_seconds() / 3600, 2),
        )
        for proof in sessions
    ]


@router.get("/sessions/{session_id}", response_model=ProofSessionResponse)
async def get_session_detail(
    session_id: uuid.UUID, user: CurrentUser, db: SessionDep
) -> ProofSessionResponse:
    proof = await _get_owned_session(session_id, user.id, db)
    return ProofSessionResponse.model_validate(proof)


# --- checks -----------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/checks",
    response_model=ProofSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def log_check(
    session_id: uuid.UUID, payload: ProofCheckCreate, user: VerifiedUser, db: SessionDep
) -> ProofSessionResponse:
    """Record what the dough is doing and re-fit the ETA.

    Returns the *session*, not the check: the point of checking in is the new
    prediction, and Phase 7 reschedules the "ready" reminder from the updated
    `predicted_end_at`.
    """
    proof = await _get_owned_session(session_id, user.id, db)
    _require_running(proof)

    now = datetime.now(UTC)
    checked_at = payload.checked_at or now
    _validate_timestamp(checked_at, now, "checked_at")
    if checked_at < proof.started_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="checked_at cannot be before the session started",
        )

    check = ProofCheck(
        session_id=proof.id, **payload.model_dump(exclude={"checked_at"}), checked_at=checked_at
    )
    db.add(check)
    await db.flush()

    coeffs = fermentation.coefficients()
    check_count = await proof_service.count_checks(db, proof.id)
    prediction = proof_service.predict_from_check(
        session=proof,
        checked_at=checked_at,
        observed_rise_pct=payload.rise_pct,
        dough_temp_c=payload.dough_temp_c,
        check_count=check_count,
        c=coeffs,
    )

    proof.predicted_end_at = prediction.predicted_end_at
    proof.window_start_at = prediction.window_start_at
    proof.window_end_at = prediction.window_end_at
    if payload.dough_temp_c is not None:
        proof.dough_temp_c = payload.dough_temp_c

    await db.flush()
    return ProofSessionResponse.model_validate(proof)


@router.get("/sessions/{session_id}/checks", response_model=list[ProofCheckResponse])
async def list_checks(
    session_id: uuid.UUID, user: CurrentUser, db: SessionDep
) -> list[ProofCheckResponse]:
    proof = await _get_owned_session(session_id, user.id, db)
    result = await db.execute(
        select(ProofCheck).where(ProofCheck.session_id == proof.id).order_by(ProofCheck.checked_at)
    )
    return [ProofCheckResponse.model_validate(c) for c in result.scalars().all()]


# --- lifecycle --------------------------------------------------------------


@router.post("/sessions/{session_id}/complete", response_model=ProofSessionResponse)
async def complete_session(
    session_id: uuid.UUID, payload: ProofCompleteRequest, user: VerifiedUser, db: SessionDep
) -> ProofSessionResponse:
    proof = await _get_owned_session(session_id, user.id, db)
    _require_running(proof)

    now = datetime.now(UTC)
    ended_at = payload.actual_end_at or now
    _validate_timestamp(ended_at, now, "actual_end_at")
    if ended_at < proof.started_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="actual_end_at cannot be before the session started",
        )

    # A final rise reading is recorded as a check, so the calibration data in
    # Phase 5+ sees the end state rather than only the intermediate glances.
    if payload.final_rise_pct is not None:
        db.add(
            ProofCheck(
                session_id=proof.id,
                checked_at=ended_at,
                rise_pct=payload.final_rise_pct,
                notes="final reading",
            )
        )

    proof.status = ProofStatus.done
    proof.actual_end_at = ended_at
    if payload.notes:
        proof.notes = payload.notes
    await db.flush()
    return ProofSessionResponse.model_validate(proof)


@router.post("/sessions/{session_id}/abort", response_model=ProofSessionResponse)
async def abort_session(
    session_id: uuid.UUID, user: VerifiedUser, db: SessionDep
) -> ProofSessionResponse:
    proof = await _get_owned_session(session_id, user.id, db)
    _require_running(proof)
    proof.status = ProofStatus.aborted
    proof.actual_end_at = datetime.now(UTC)
    await db.flush()
    return ProofSessionResponse.model_validate(proof)
