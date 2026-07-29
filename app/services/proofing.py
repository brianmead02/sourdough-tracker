"""Proof session orchestration: predictions, re-fitting, and starter vigour."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.proofing import ProofCheck, ProofSession
from app.models.starter import Feeding, StarterObservation
from app.services import fermentation

# How many recent peak observations feed the vigour estimate. Enough to smooth
# noise, few enough that a starter that has since been revived is not judged on
# how it behaved a month ago.
VIGOUR_SAMPLE_SIZE = 8


@dataclass(slots=True)
class Prediction:
    predicted_end_at: datetime
    window_start_at: datetime
    window_end_at: datetime
    remaining_hours: float


def _window(
    origin: datetime, remaining_hours: float, check_count: int, c: fermentation.Coefficients
) -> Prediction:
    low, high = fermentation.confidence_window(remaining_hours, check_count, c)
    return Prediction(
        predicted_end_at=origin + timedelta(hours=remaining_hours),
        window_start_at=origin + timedelta(hours=low),
        window_end_at=origin + timedelta(hours=high),
        remaining_hours=round(remaining_hours, 3),
    )


def predict_from_start(
    *,
    started_at: datetime,
    target_rise_pct: float,
    planned_duration_minutes: int | None,
    dough_temp_c: float,
    starter_pct: float,
    vigour: float,
    c: fermentation.Coefficients,
) -> Prediction:
    """The initial estimate, before any checks."""
    if target_rise_pct <= 0:
        # Time-based stage (autolyse): a rest of a fixed length, not a ferment.
        minutes = planned_duration_minutes or 0
        return Prediction(
            predicted_end_at=started_at + timedelta(minutes=minutes),
            window_start_at=started_at + timedelta(minutes=minutes),
            window_end_at=started_at + timedelta(minutes=minutes),
            remaining_hours=round(minutes / 60, 3),
        )

    hours = fermentation.predict_duration_hours(
        target_rise_pct, dough_temp_c, starter_pct, vigour, c
    )
    return _window(started_at, hours, 0, c)


def predict_from_check(
    *,
    session: ProofSession,
    checked_at: datetime,
    observed_rise_pct: float,
    dough_temp_c: float | None,
    check_count: int,
    c: fermentation.Coefficients,
) -> Prediction:
    """Re-fit the estimate against what the dough is actually doing.

    Anchored at the moment of the check, not at the start: the remaining time is
    what the baker cares about, and it keeps the window from being distorted by
    however long the proof has already run.
    """
    temp = dough_temp_c if dough_temp_c is not None else session.dough_temp_c
    elapsed_hours = (checked_at - session.started_at).total_seconds() / 3600
    model_rate = fermentation.predict_rate(temp, session.starter_pct, session.vigour_used, c)

    remaining = fermentation.refit_remaining_hours(
        target_rise_pct=session.target_rise_pct,
        observed_rise_pct=observed_rise_pct,
        elapsed_hours=elapsed_hours,
        model_rate=model_rate,
        check_count=check_count,
    )
    return _window(checked_at, remaining, check_count, c)


async def estimate_starter_vigour(
    session: AsyncSession, starter_id: uuid.UUID | None, c: fermentation.Coefficients
) -> float:
    """Vigour from the starter's recent time-to-peak observations.

    Needs an observation marked `peaked` that is linked to the feeding it
    followed — without the feeding there is no start time to measure from.
    """
    if starter_id is None:
        return 1.0

    result = await session.execute(
        select(
            StarterObservation.observed_at,
            StarterObservation.dough_temp_c,
            Feeding.fed_at,
            Feeding.ambient_temp_c,
        )
        .join(Feeding, Feeding.id == StarterObservation.feeding_id)
        .where(
            StarterObservation.starter_id == starter_id,
            StarterObservation.peaked.is_(True),
        )
        .order_by(StarterObservation.observed_at.desc())
        .limit(VIGOUR_SAMPLE_SIZE)
    )

    peaks: list[tuple[float, float | None]] = []
    for observed_at, dough_temp, fed_at, ambient_temp in result.all():
        hours = (observed_at - fed_at).total_seconds() / 3600
        if hours > 0:
            peaks.append((hours, dough_temp if dough_temp is not None else ambient_temp))

    return fermentation.estimate_vigour(peaks, c)


async def count_checks(session: AsyncSession, session_id: uuid.UUID) -> int:
    result = await session.execute(select(ProofCheck.id).where(ProofCheck.session_id == session_id))
    return len(result.all())


def progress_pct(session: ProofSession, latest_rise_pct: float | None, now: datetime) -> float:
    """How far along, 0-100, for a progress bar.

    Rise-based when there is an observation to go on, otherwise elapsed time
    against the prediction.
    """
    if session.is_time_based or latest_rise_pct is None:
        total = (session.predicted_end_at - session.started_at).total_seconds()
        if total <= 0:
            return 100.0
        elapsed = (now - session.started_at).total_seconds()
        return round(min(max(elapsed / total * 100, 0.0), 100.0), 1)

    if session.target_rise_pct <= 0:
        return 100.0
    return round(min(max(latest_rise_pct / session.target_rise_pct * 100, 0.0), 100.0), 1)


def now_utc() -> datetime:
    return datetime.now(UTC)
