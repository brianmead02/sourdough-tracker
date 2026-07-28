"""Request/response models for the auth endpoints."""

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.validators import validate_handle, validate_password, validate_timezone


class RegisterRequest(BaseModel):
    email: EmailStr
    # Upper bound guards against argon2 CPU exhaustion via huge inputs.
    password: str = Field(max_length=128)
    handle: str
    display_name: str = Field(min_length=1, max_length=60)
    timezone: str = "UTC"

    _check_password = field_validator("password")(validate_password)
    _check_handle = field_validator("handle")(validate_handle)
    _check_timezone = field_validator("timezone")(validate_timezone)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(max_length=128)

    _check_password = field_validator("new_password")(validate_password)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)

    _check_password = field_validator("new_password")(validate_password)


class MessageResponse(BaseModel):
    message: str
