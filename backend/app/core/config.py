import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    FILES_FOLDER: str = "/files"
    SECRET_KEY: str = ""
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    @model_validator(mode="after")
    def _check_secret_key(self) -> Self:
        if not self.SECRET_KEY:
            # Generate a random key only if not provided (for development)
            self.SECRET_KEY = secrets.token_urlsafe(32)
            warnings.warn(
                "SECRET_KEY not set in environment. Using a random key. "
                "This will invalidate tokens on restart!",
                stacklevel=1
            )
        return self

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str = "FastAPI Ecommerce"
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_SSL_MODE: str = "allow"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return MultiHostUrl.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    REDIS_SERVER: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_CELERY_DB_INDEX: int = 1
    REDIS_USER: str = ""
    REDIS_PASSWORD: str = ""
    REDIS_CELERY_USER: str = ""
    REDIS_CELERY_PASSWORD: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_USER and self.REDIS_PASSWORD:
            return (
                f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_SERVER}:{self.REDIS_PORT}"
            )
        return f"redis://{self.REDIS_SERVER}:{self.REDIS_PORT}"

    EMAILS_FROM_EMAIL: str | None = None
    EMAILS_FROM_NAME: str | None = None
    EMAILS_API_URL: HttpUrl | None = None
    EMAILS_API_KEY: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.EMAILS_API_URL and self.EMAILS_API_KEY)

    # TODO: update type to EmailStr when sqlmodel supports it
    EMAIL_TEST_USER: str = "test@example.com"
    # TODO: update type to EmailStr when sqlmodel supports it
    FIRST_SUPERUSER: str = "jburckel@natimai.solutions"
    FIRST_SUPERUSER_PASSWORD: str = "changethisA1"
    EMAIL_SUPPORT: str | None = None
    EMAIL_CONTACT: str | None = None

    # AI
    OPENAI_ORG_ID: str | None = None
    OPENAI_API_KEY: str | None = None

    # Ingram Micro API Configuration
    INGRAM_CLIENT_ID: str | None = None
    INGRAM_CLIENT_SECRET: str | None = None
    INGRAM_CUSTOMER_NUMBER: str | None = None
    INGRAM_COUNTRY_CODE: str = "FR"  # Default to FR, can be changed via env var
    INGRAM_ENVIRONMENT: Literal["sandbox", "production"] = "sandbox"
    INGRAM_SYNC_ENABLED: bool = True
    INGRAM_SYNC_CATEGORIES: list[str] = [
        "Ordinateur/Serveur",
    ]
    INGRAM_SYNC_INTERVAL_HOURS: int = 6  # Synchronisation toutes les 6 heures

    # Icecat API Configuration
    ICECAT_USERNAME: str | None = None
    ICECAT_API_KEY: str | None = None
    ICECAT_LANGUAGE: str = "fr"  # Default language
    ICECAT_ENABLED: bool = True  # Enable/disable Icecat enrichment

    # S3
    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_KEY_ID: str | None = None
    S3_BUCKET_NAME: str | None = None

    # PayZen Configuration
    PAYZEN_SITE_ID: str | None = None
    PAYZEN_API_PASSWORD_TEST: str | None = None
    PAYZEN_API_PASSWORD_PROD: str | None = None
    PAYZEN_PUBLIC_KEY_TEST: str | None = None
    PAYZEN_PUBLIC_KEY_PROD: str | None = None
    PAYZEN_MODE: Literal["TEST", "PRODUCTION"] = "TEST"
    PAYZEN_API_ENDPOINT: str = "https://api.osb.pf"
    PAYZEN_CURRENCY: str = "XPF"  # Default currency for French Polynesia
    PAYZEN_IPN_URL: str | None = None  # Will be computed based on backend URL
    PAYZEN_RETURN_URL: str | None = None  # Frontend URL to return after payment

    @computed_field  # type: ignore[prop-decorator]
    @property
    def payzen_ipn_url_computed(self) -> str:
        """Compute the PayZen IPN URL based on backend configuration."""
        if self.PAYZEN_IPN_URL:
            return self.PAYZEN_IPN_URL
        # Default to API endpoint + payment/payzen/ipn
        backend_url = str(self.BACKEND_CORS_ORIGINS[0]) if self.BACKEND_CORS_ORIGINS else "http://localhost:8000"
        return f"{backend_url}{self.API_V1_STR}/payment/payzen/ipn"

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore
