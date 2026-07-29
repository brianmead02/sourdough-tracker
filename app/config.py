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

    # --- notifications -------------------------------------------------------
    # Web Push. Generate a pair with `sdt vapid-keys`; without them the Web Push
    # channel is simply unavailable rather than broken.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@sourdough.local"
    # How many due rows one beat tick claims. Bounded so a backlog drains over
    # several ticks instead of one enormous transaction.
    notification_batch_size: int = 100
    notification_max_attempts: int = 4
    notification_retry_base_seconds: int = 60
    # Reminders are pointless once they are this stale — the dough is long done.
    notification_stale_after_hours: int = 12

    # --- fermentation model (docs/PLAN.md §5) --------------------------------
    # These are tuning knobs, not constants: the model is wrong until calibrated
    # against real observed-vs-predicted data, and must be adjustable without a
    # code change.
    ferment_ref_temp_c: float = 24.0
    # Rise fraction per hour at reference temperature and inoculation, i.e. 0.15
    # means a 75% bulk rise takes 5 hours.
    ferment_base_rise_per_hour: float = 0.15
    # Rate multiplier per 10 degrees. Yeast slows disproportionately in the cold,
    # so a single Q10 across 4-30C badly under-predicts retard times; the curve is
    # piecewise and continuous at the threshold.
    ferment_q10_warm: float = 2.0
    ferment_q10_cold: float = 3.0
    ferment_cold_threshold_c: float = 15.0
    ferment_ref_starter_pct: float = 20.0
    # Sub-linear: doubling the starter does not halve the time.
    ferment_inoculation_exponent: float = 0.7
    # Hours for a reference starter to peak at reference temperature.
    ferment_ref_peak_hours: float = 6.0
    ferment_vigour_min: float = 0.5
    ferment_vigour_max: float = 2.0
    # Half-width of the prediction window as a fraction of the estimate, before
    # any checks have been logged, and the floor it converges towards.
    ferment_base_spread: float = 0.35
    ferment_min_spread: float = 0.08

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
    # Presigned URLs are handed to browsers and phones, which cannot resolve the
    # compose-internal hostname. Set this to the address clients can reach.
    minio_public_endpoint: str = ""
    minio_region: str = "us-east-1"

    # --- media uploads -------------------------------------------------------
    upload_url_ttl_seconds: int = 900
    download_url_ttl_seconds: int = 3600
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_image_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )

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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def minio_internal_url(self) -> str:
        scheme = "https" if self.minio_secure else "http"
        return f"{scheme}://{self.minio_endpoint}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def minio_client_url(self) -> str:
        """Endpoint baked into presigned URLs. Falls back to the internal one."""
        return self.minio_public_endpoint or self.minio_internal_url

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
