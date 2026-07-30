"""Shared FastAPI dependencies: authentication, authorisation, rate limiting."""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models.user import User, UserRole
from app.services.measurements import System
from app.services.security import TokenError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise CREDENTIALS_EXCEPTION from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise CREDENTIALS_EXCEPTION from exc

    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise CREDENTIALS_EXCEPTION

    # Checked per request, not baked into the token: a suspension must take
    # effect before the current access token would have expired.
    if user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_verified_user(user: CurrentUser) -> User:
    """For actions that must not be available to unconfirmed addresses."""
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Confirm your email address to use this feature",
        )
    return user


VerifiedUser = Annotated[User, Depends(get_verified_user)]


async def get_units(
    user: CurrentUser,
    units: Annotated[System | None, Query(description="Override the profile default")] = None,
) -> System:
    """Which system to render quantities in: the query wins, else the profile.

    A per-request override matters because recipes are shared. A recipe authored
    by a baker who works in cups is read by one who works in grams, and the
    reader's preference is the one that should win — with a way to ask for the
    other without changing their account.
    """
    if units is not None:
        return units
    profile = user.profile
    try:
        return System(profile.units) if profile else System.metric
    except ValueError:
        # An unrecognised stored value must not break every read path.
        return System.metric


UnitsPref = Annotated[System, Depends(get_units)]

_ROLE_RANK = {UserRole.user: 0, UserRole.moderator: 1, UserRole.admin: 2}


def require_role(minimum: UserRole) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Dependency factory gating a route on a minimum role."""

    async def _dependency(user: CurrentUser) -> User:
        if _ROLE_RANK[user.role] < _ROLE_RANK[minimum]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dependency


# --- rate limiting ----------------------------------------------------------


def client_ip(request: Request) -> str:
    """Best-effort client address.

    Only the left-most X-Forwarded-For entry is used, and only because the app is
    always deployed behind Caddy (docs/PLAN.md §8). Exposing the API directly
    would make this header attacker-controlled.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """Fixed-window limiter backed by Redis, shared across API replicas.

    Fixed windows can allow up to 2x the limit across a window boundary. That is
    an accepted trade for these endpoints — the goal is blunting credential
    stuffing and signup floods, not precise quota accounting.
    """

    def __init__(self, times: int, seconds: int, scope: str) -> None:
        self.times = times
        self.seconds = seconds
        self.scope = scope

    async def __call__(self, request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        key = f"ratelimit:{self.scope}:{client_ip(request)}"
        client = aioredis.from_url(settings.redis_url)
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, self.seconds)
            if count > self.times:
                retry_after = await client.ttl(key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Try again shortly.",
                    headers={"Retry-After": str(max(retry_after, 1))},
                )
        except aioredis.RedisError:
            # Redis down must not lock everyone out of logging in.
            return
        finally:
            await client.aclose()
