"""Authentication business logic, kept out of the routers."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import (
    EmailVerification,
    PasswordReset,
    RefreshToken,
    User,
    UserProfile,
    UserRole,
)
from app.services import security

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Credentials rejected, or the account may not log in."""


class TokenReuseError(AuthError):
    """A revoked refresh token was presented — treated as a leak."""


@dataclass(slots=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int


# --- registration -----------------------------------------------------------


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(
        select(User).where(User.email == email.lower(), User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def handle_taken(session: AsyncSession, handle: str) -> bool:
    result = await session.execute(
        select(UserProfile.user_id).where(UserProfile.handle == handle.lower())
    )
    return result.first() is not None


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    handle: str,
    display_name: str,
    timezone: str = "UTC",
    role: UserRole = UserRole.user,
) -> User:
    user = User(
        email=email.lower(),
        password_hash=security.hash_password(password),
        role=role,
    )
    user.profile = UserProfile(
        handle=handle.lower(),
        display_name=display_name,
        timezone=timezone,
    )
    session.add(user)
    await session.flush()
    return user


# --- single-use tokens ------------------------------------------------------


async def issue_email_verification(session: AsyncSession, user: User) -> str:
    settings = get_settings()
    token = security.generate_token()
    now = datetime.now(UTC)
    session.add(
        EmailVerification(
            user_id=user.id,
            token_hash=security.hash_token(token),
            created_at=now,
            expires_at=now + timedelta(hours=settings.email_verification_ttl_hours),
        )
    )
    return token


async def consume_email_verification(session: AsyncSession, token: str) -> User:
    result = await session.execute(
        select(EmailVerification).where(EmailVerification.token_hash == security.hash_token(token))
    )
    record = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise AuthError("verification link is invalid or has expired")

    user = await session.get(User, record.user_id)
    if user is None or user.deleted_at is not None:
        raise AuthError("verification link is invalid or has expired")

    record.used_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now
    return user


async def issue_password_reset(session: AsyncSession, user: User) -> str:
    settings = get_settings()
    token = security.generate_token()
    now = datetime.now(UTC)
    session.add(
        PasswordReset(
            user_id=user.id,
            token_hash=security.hash_token(token),
            created_at=now,
            expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    return token


async def consume_password_reset(session: AsyncSession, token: str, new_password: str) -> User:
    result = await session.execute(
        select(PasswordReset).where(PasswordReset.token_hash == security.hash_token(token))
    )
    record = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise AuthError("reset link is invalid or has expired")

    user = await session.get(User, record.user_id)
    if user is None or user.deleted_at is not None:
        raise AuthError("reset link is invalid or has expired")

    record.used_at = now
    user.password_hash = security.hash_password(new_password)
    # A reset is a recovery action: assume the old sessions are not trustworthy.
    await revoke_all_refresh_tokens(session, user.id)
    return user


# --- login ------------------------------------------------------------------


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(session, email)

    if user is None:
        security.spend_dummy_hash()
        raise AuthError("incorrect email or password")

    if not security.verify_password(password, user.password_hash):
        raise AuthError("incorrect email or password")

    if user.is_suspended:
        raise AuthError("this account has been suspended")

    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)

    user.last_login_at = datetime.now(UTC)
    return user


# --- refresh tokens ---------------------------------------------------------


async def issue_refresh_token(
    session: AsyncSession,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> str:
    settings = get_settings()
    token = security.generate_token()
    now = datetime.now(UTC)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=security.hash_token(token),
            family_id=family_id or uuid.uuid4(),
            issued_at=now,
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:255] or None,
            client_ip=client_ip,
        )
    )
    return token


async def issue_tokens(
    session: AsyncSession,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> IssuedTokens:
    access, expires_in = security.create_access_token(user.id, user.role.value)
    refresh = await issue_refresh_token(
        session, user, family_id=family_id, user_agent=user_agent, client_ip=client_ip
    )
    return IssuedTokens(access_token=access, refresh_token=refresh, expires_in=expires_in)


async def rotate_refresh_token(
    session: AsyncSession,
    token: str,
    *,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> IssuedTokens:
    """Exchange a refresh token for a new pair, revoking the presented one.

    Presenting an already-revoked token means it leaked: the legitimate client
    already rotated it, so someone replayed a copy. The entire family is revoked,
    forcing both parties to log in again.
    """
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(token))
    )
    record = result.scalar_one_or_none()
    now = datetime.now(UTC)

    if record is None:
        raise AuthError("invalid refresh token")

    if record.revoked_at is not None:
        logger.warning(
            "refresh token reuse detected user_id=%s family_id=%s", record.user_id, record.family_id
        )
        await revoke_family(session, record.family_id)
        # Commit before raising. This request ends in a 401, and get_session()
        # rolls back on exception — which would silently discard the revocation
        # and leave the stolen session alive.
        await session.commit()
        raise TokenReuseError("refresh token has already been used")

    if record.expires_at <= now:
        raise AuthError("refresh token has expired")

    user = await session.get(User, record.user_id)
    if user is None or user.deleted_at is not None:
        raise AuthError("invalid refresh token")
    if user.is_suspended:
        raise AuthError("this account has been suspended")

    record.revoked_at = now
    return await issue_tokens(
        session,
        user,
        family_id=record.family_id,
        user_agent=user_agent,
        client_ip=client_ip,
    )


async def revoke_refresh_token(session: AsyncSession, token: str) -> None:
    """Logout. Silent when the token is unknown — nothing to disclose."""
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == security.hash_token(token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )


async def revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def revoke_all_refresh_tokens(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
