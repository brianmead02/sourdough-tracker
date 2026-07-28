"""Registration, login, token rotation, email verification and password reset."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, RateLimiter, client_ip
from app.db import get_session
from app.queue import enqueue
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.schemas.user import CurrentUserResponse
from app.services import auth as auth_service
from app.services import email as email_templates
from app.services import security
from app.services.auth import AuthError, TokenReuseError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Identical wording for every "we may have sent you something" response, so the
# API never reveals which addresses are registered.
_GENERIC_EMAIL_SENT = "If that address needs action, an email is on its way."


async def _send(to: str, subject_body: tuple[str, str]) -> None:
    subject, body = subject_body
    await enqueue("send_email", to, subject, body)


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(RateLimiter(times=5, seconds=3600, scope="register"))],
)
async def register(payload: RegisterRequest, session: SessionDep) -> MessageResponse:
    """Create an account.

    Returns the same response whether or not the email is already registered.
    A handle collision *is* reported (409) — handles are public by design.
    """
    if await auth_service.handle_taken(session, payload.handle):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That handle is already taken"
        )

    existing = await auth_service.get_user_by_email(session, payload.email)
    if existing is not None:
        await _send(existing.email, email_templates.duplicate_signup_email(existing.email))
        return MessageResponse(message=_GENERIC_EMAIL_SENT)

    user = await auth_service.create_user(
        session,
        email=payload.email,
        password=payload.password,
        handle=payload.handle,
        display_name=payload.display_name,
        timezone=payload.timezone,
    )
    token = await auth_service.issue_email_verification(session, user)
    await _send(user.email, email_templates.verification_email(payload.handle, token))
    logger.info("registered user handle=%s", payload.handle)
    return MessageResponse(message=_GENERIC_EMAIL_SENT)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(payload: VerifyEmailRequest, session: SessionDep) -> MessageResponse:
    try:
        await auth_service.consume_email_verification(session, payload.token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Email address confirmed.")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    dependencies=[Depends(RateLimiter(times=3, seconds=3600, scope="resend-verification"))],
)
async def resend_verification(
    payload: ResendVerificationRequest, session: SessionDep
) -> MessageResponse:
    user = await auth_service.get_user_by_email(session, payload.email)
    if user is not None and not user.is_verified:
        token = await auth_service.issue_email_verification(session, user)
        await _send(user.email, email_templates.verification_email(user.profile.handle, token))
    return MessageResponse(message=_GENERIC_EMAIL_SENT)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(RateLimiter(times=10, seconds=900, scope="login"))],
)
async def login(payload: LoginRequest, request: Request, session: SessionDep) -> TokenResponse:
    try:
        user = await auth_service.authenticate(session, payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    tokens = await auth_service.issue_tokens(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
        client_ip=client_ip(request),
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(RateLimiter(times=60, seconds=3600, scope="refresh"))],
)
async def refresh(payload: RefreshRequest, request: Request, session: SessionDep) -> TokenResponse:
    try:
        tokens = await auth_service.rotate_refresh_token(
            session,
            payload.refresh_token,
            user_agent=request.headers.get("user-agent"),
            client_ip=client_ip(request),
        )
    except TokenReuseError as exc:
        # The family is already revoked; tell the client to start over.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated. Please log in again.",
        ) from exc
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(payload: RefreshRequest, session: SessionDep) -> MessageResponse:
    await auth_service.revoke_refresh_token(session, payload.refresh_token)
    return MessageResponse(message="Logged out.")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(RateLimiter(times=5, seconds=3600, scope="forgot-password"))],
)
async def forgot_password(payload: ForgotPasswordRequest, session: SessionDep) -> MessageResponse:
    user = await auth_service.get_user_by_email(session, payload.email)
    if user is not None:
        token = await auth_service.issue_password_reset(session, user)
        await _send(user.email, email_templates.password_reset_email(user.profile.handle, token))
    return MessageResponse(message=_GENERIC_EMAIL_SENT)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, session: SessionDep) -> MessageResponse:
    try:
        await auth_service.consume_password_reset(session, payload.token, payload.new_password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Password changed. All sessions have been signed out.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, session: SessionDep
) -> MessageResponse:
    if not security.verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    user.password_hash = security.hash_password(payload.new_password)
    await auth_service.revoke_all_refresh_tokens(session, user.id)
    return MessageResponse(message="Password changed. All sessions have been signed out.")


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(user)
