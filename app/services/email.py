"""Transactional email.

Phase 7 wraps this in the multi-channel `Notifier` interface; for now it is the
one outbound channel and is always called from a worker, never inline in a
request, so SMTP latency cannot block an API response.
"""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body: str) -> None:
    settings = get_settings()

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        # Mailhog and most relays on 25/1025 speak plaintext; 587 upgrades.
        start_tls=settings.smtp_port == 587,
    )
    logger.info("sent email subject=%r to=%s", subject, to)


def verification_email(handle: str, token: str) -> tuple[str, str]:
    link = f"{get_settings().public_base_url}/verify-email?token={token}"
    ttl = get_settings().email_verification_ttl_hours
    return (
        "Confirm your Sourdough Tracker account",
        f"Hi {handle},\n\n"
        f"Confirm your email address to activate your account:\n\n{link}\n\n"
        f"This link expires in {ttl} hours. If you did not sign up, ignore this email.\n",
    )


def password_reset_email(handle: str, token: str) -> tuple[str, str]:
    link = f"{get_settings().public_base_url}/reset-password?token={token}"
    ttl = get_settings().password_reset_ttl_minutes
    return (
        "Reset your Sourdough Tracker password",
        f"Hi {handle},\n\n"
        f"Reset your password here:\n\n{link}\n\n"
        f"This link expires in {ttl} minutes. If you did not request a reset, "
        f"ignore this email — your password has not changed.\n",
    )


def duplicate_signup_email(email: str) -> tuple[str, str]:
    """Sent when someone tries to register an address that already exists.

    Registration returns an identical response either way to avoid disclosing
    which addresses are registered; this tells the real owner what happened.
    """
    link = f"{get_settings().public_base_url}/forgot-password"
    return (
        "Someone tried to sign up with your email",
        f"An account already exists for {email}.\n\n"
        f"If that was you, reset your password instead:\n\n{link}\n\n"
        f"If it wasn't, no action is needed — no new account was created.\n",
    )
