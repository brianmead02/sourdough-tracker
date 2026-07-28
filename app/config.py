"""Application settings, loaded from environment / .env."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# >= 32 bytes: HS256 keys shorter than the digest weaken the MAC (RFC 7518 §3.2).
DEFAULT_JWT_SECRET = "dev-only-insecure-change-me-before-deploying"
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- app -----------------------------------------------------------------
    app_name: str = "Sourdough Tracker"
    environment: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8000"])
    # Base URL used to build links in transactional email.
    public_base_url: str = "http://localhost:8000"

    # --- auth ----------------------------------------------------------------
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    email_verification_ttl_hours: int = 48
    password_reset_ttl_minutes: int = 60
    password_min_length: int = 10
    # argon2id cost parameters
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536  # KiB
    argon2_parallelism: int = 4

    # --- rate limiting -------------------------------------------------------
    rate_limit_enabled: bool = True

    # --- postgres ------------------------------------------------------------
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "sourdough"
    postgres_password: str = "sourdough"
    postgres_db: str = "sourdough"

    # --- redis ---------------------------------------------------------------
    redis_url: str = "redis://redis:6379/0"

    # --- minio / s3 ----------------------------------------------------------
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "sourdough-media"
    minio_secure: bool = False

    # --- smtp ----------------------------------------------------------------
    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Sourdough Tracker <no-reply@sourdough.local>"

    # --- ntfy ----------------------------------------------------------------
    ntfy_base_url: str = "http://ntfy:80"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_dev(self) -> bool:
        return self.environment == "dev"

    @model_validator(mode="after")
    def _reject_insecure_secrets(self) -> "Settings":
        """Fail fast rather than serve traffic with a weak or shipped-default secret."""
        if len(self.jwt_secret) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters "
                "(HS256 keys shorter than the digest weaken the signature)"
            )
        if self.environment == "prod" and self.jwt_secret == DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set to a unique value when ENVIRONMENT=prod")
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Call `get_settings.cache_clear()` in tests."""
    return Settings()
