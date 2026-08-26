import secrets
import warnings
from decimal import Decimal
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

from app.features.integrations.services.supplier_data_normalization import (
    ProductFilterRule,
)


def parse_cors(v: Any) -> list[str] | str:
    """Parse cors."""
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    """Represents settings."""

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

    # Refresh-token cookie. The access token lives only in the SPA memory; the
    # refresh token is delivered as an HttpOnly cookie so JS (and thus XSS) can
    # never read it. Path is scoped to the login routes (see auth_cookies.py).
    REFRESH_COOKIE_NAME: str = "refresh_token"
    REFRESH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    REFRESH_COOKIE_DOMAIN: str | None = None
    # None → derive from ENVIRONMENT (Secure disabled only for local http dev).
    REFRESH_COOKIE_SECURE: bool | None = None

    @property
    def refresh_cookie_secure(self) -> bool:
        """Whether the refresh cookie carries the Secure attribute."""
        if self.REFRESH_COOKIE_SECURE is not None:
            return self.REFRESH_COOKIE_SECURE
        return self.ENVIRONMENT != "local"

    def _check_secret_key(self) -> None:
        """Empty SECRET_KEY: generated (with a warning) in local, fatal elsewhere.

        A random per-process key outside local would silently invalidate every
        JWT at each restart — and across replicas — while masking the missing
        configuration. Called from ``_enforce_non_default_secrets``.
        """
        if not self.SECRET_KEY:
            if self.ENVIRONMENT != "local":
                raise ValueError(
                    "SECRET_KEY is not set. Generate one (`openssl rand -base64 32`) "
                    "and set it in the environment — required for any non-local "
                    "deployment."
                )
            # Generate a random key only if not provided (local development)
            self.SECRET_KEY = secrets.token_urlsafe(32)
            warnings.warn(
                "SECRET_KEY not set in environment. Using a random key. "
                "This will invalidate tokens on restart!",
                stacklevel=1,
            )

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        """Execute all cors origins."""
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str = "FastAPI Ecommerce"
    SENTRY_DSN: HttpUrl | None = None
    # Webhook d'alerte opérationnelle (format Slack `{"text": …}`) — utilisé par
    # le health-checker outbox et par l'abandon définitif d'un job ARQ.
    # Vide = pas d'alerte (log uniquement).
    ALERT_WEBHOOK_URL: str | None = None
    POSTGRES_SERVER: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_SSL_MODE: str = "allow"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        """Execute SQLALCHEMY DATABASE URI."""
        return MultiHostUrl.build(  # type: ignore[return-value]
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
        """Execute REDIS URL."""
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
        """Set default emails from."""
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        """Execute emails enabled."""
        return bool(self.EMAILS_API_URL and self.EMAILS_API_KEY)

    # TODO: update type to EmailStr when sqlmodel supports it
    EMAIL_TEST_USER: str = "test@example.com"
    # TODO: update type to EmailStr when sqlmodel supports it
    # Override in .env — these are placeholder defaults only.
    FIRST_SUPERUSER: str = "admin@example.com"
    FIRST_SUPERUSER_PASSWORD: str = "changethis"
    EMAIL_SUPPORT: str | None = None
    EMAIL_CONTACT: str | None = None

    # AI
    OPENAI_ORG_ID: str | None = None
    OPENAI_API_KEY: str | None = None

    # Supplier sync eligibility thresholds — products below either threshold
    # are created/updated with is_active=False and hidden from the storefront.
    # Set to 0 to disable filtering (default: show everything).
    SUPPLIER_SYNC_MIN_QUANTITY: Decimal = Decimal("0")
    SUPPLIER_SYNC_MIN_PRICE: Decimal = Decimal("0")

    # Product category filter rules.
    # Level 1 (import): supplier_subcategory / supplier_category / name_keyword
    # Level 2 (post-enrichment): unspsc_code
    # action: "deactivate" (keep in DB, is_active=False) or "skip" (don't import at all)
    # Override via env var as JSON: SUPPLIER_PRODUCT_FILTER_RULES='[{"field":"supplier_subcategory","values":["Garantie Ordinateur"]}]'
    SUPPLIER_PRODUCT_FILTER_RULES: list[ProductFilterRule] = [
        ProductFilterRule(field="supplier_subcategory", values=["Garantie Ordinateur"]),
        ProductFilterRule(field="unspsc_code", values=["81111812"]),
    ]

    # Subcategory allowlist (curation). When non-empty, ONLY products whose
    # supplier_subcategory matches (case-insensitive) are kept active; everything
    # else is deactivated on the next sync (hidden from the storefront, kept in
    # DB). Empty = no allowlist filtering (keep everything). Tune via env var:
    # SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST='["Ordinateur de Bureau/Tour","Ordinateur Portable"]'
    SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST: list[str] = [
        "Ordinateur de Bureau/Tour",
        "Ordinateur Portable",
    ]

    # Ingram Micro API Configuration
    INGRAM_CLIENT_ID: str | None = None
    INGRAM_CLIENT_SECRET: str | None = None
    INGRAM_CUSTOMER_NUMBER: str | None = None
    INGRAM_COUNTRY_CODE: str = "FR"  # Default to FR, can be changed via env var
    # Place.code identifying where Ingram products ship from (drives the first
    # logistics leg). Seeded by initial_data as "FR_SUPPLIERS".
    INGRAM_ORIGIN_PLACE_CODE: str = "FR_SUPPLIERS"
    INGRAM_ENVIRONMENT: Literal["sandbox", "production"] = "sandbox"
    INGRAM_SYNC_ENABLED: bool = True
    INGRAM_SYNC_CATEGORIES: list[str] = [
        "Ordinateur/Serveur",
    ]
    INGRAM_SYNC_INTERVAL_HOURS: int = 6  # Synchronisation toutes les 6 heures

    # Ingram Micro — automatic purchase order creation on payment.captured
    # Enable only after INGRAM_SHIP_TO_* fields are configured.
    INGRAM_ORDER_CREATION_ENABLED: bool = False
    INGRAM_SHIP_TO_CONTACT: str | None = None
    INGRAM_SHIP_TO_COMPANY_NAME: str | None = None
    INGRAM_SHIP_TO_ADDRESS_LINE1: str | None = None
    INGRAM_SHIP_TO_CITY: str | None = None
    INGRAM_SHIP_TO_POSTAL_CODE: str | None = None
    INGRAM_SHIP_TO_COUNTRY_CODE: str = "PF"
    INGRAM_SHIP_TO_PHONE: str | None = None
    # Shared secret used to authenticate inbound Ingram webhook calls.
    # Ingram sends this token in the Authorization: Bearer <token> header.
    INGRAM_WEBHOOK_SECRET: str | None = None

    # Icecat API Configuration
    ICECAT_USERNAME: str | None = None
    ICECAT_API_KEY: str | None = None
    ICECAT_LANGUAGE: str = "fr"  # Default language
    ICECAT_ENABLED: bool = True  # Enable/disable Icecat enrichment
    ICECAT_USE_OPEN: bool = True  # Use Open Icecat (free) instead of Full Icecat (paid)
    # Recurring batch enrichment: drains the backlog of un-enriched products so
    # the storefront (which only shows is_enriched=True) fills up over time,
    # independently of whether a product sync created new products.
    # Interval in hours (0 = disable the cron). Each run processes up to
    # ICECAT_BATCH_ENRICH_LIMIT products and re-enqueues itself while a full
    # batch is found, so the backlog drains within minutes rather than per-tick.
    ICECAT_ENRICHMENT_CRON_INTERVAL_HOURS: int = 1
    ICECAT_BATCH_ENRICH_LIMIT: int = 50
    # Products that returned no Icecat match (or errored) are stamped and not
    # retried until this cooldown elapses — avoids hammering Icecat every run
    # with the same un-matchable SKUs and guarantees the batch loop terminates.
    ICECAT_ENRICHMENT_RETRY_COOLDOWN_DAYS: int = 7

    # S3
    S3_ENDPOINT_URL: str | None = None
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_KEY_ID: str | None = None
    S3_BUCKET_NAME: str | None = None
    S3_REGION: str = "us-east-1"

    # File storage backend selection for payment attachments
    FILE_STORAGE_BACKEND: Literal["s3", "local"] = "local"
    FILE_STORAGE_LOCAL_ROOT: str = "/tmp/fastapi_ecommerce_storage"
    FILE_STORAGE_PRESIGNED_TTL_SECONDS: int = 300

    # Payment attachment validation
    PAYMENT_ATTACHMENT_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    PAYMENT_ATTACHMENT_ALLOWED_MIME: list[str] = [
        "application/pdf",
        "image/jpeg",
        "image/png",
    ]

    # Payment event notifications
    PAYMENT_NOTIFICATIONS_EMAIL_ENABLED: bool = True
    PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER: str = "noop"
    PAYMENT_NOTIFICATIONS_SLACK_ENABLED: bool = False
    PAYMENT_NOTIFICATIONS_SLACK_PROVIDER: str = "slack_webhook"
    PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL: HttpUrl | None = None

    # Mailgun notification provider
    MAILGUN_API_BASE_URL: str = "https://api.mailgun.net/v3"
    MAILGUN_DOMAIN: str | None = None
    MAILGUN_API_KEY: str | None = None
    MAILGUN_FROM_EMAIL: str | None = None
    MAILGUN_FROM_NAME: str | None = None
    MAILGUN_TIMEOUT_SECONDS: int = 10

    # Group-based permissions (RBAC)
    # Set to True in Phase 2 after security groups are seeded and assigned.
    # When False, all authenticated users pass permission checks (current behavior).
    ENABLE_GROUP_PERMISSIONS: bool = False

    # --- Login hardening -------------------------------------------------
    # Per-IP throttle on POST /login/access-token (Redis-backed, fail-open).
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 10
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 60
    # Per-account lockout: after N consecutive wrong passwords the account is
    # locked for LOGIN_LOCKOUT_MINUTES (counter resets on successful login).
    LOGIN_LOCKOUT_MAX_FAILURES: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    # Behind Cloudflare / a reverse proxy the socket IP is the proxy's, not the
    # client's: name the trusted header carrying the real client IP —
    # "CF-Connecting-IP" (Cloudflare) or "X-Forwarded-For" (nginx/traefik with
    # a sanitized XFF). Leave None when the app is directly exposed, otherwise
    # the header could be spoofed to bypass the per-IP throttle.
    CLIENT_IP_HEADER: str | None = None

    # Shop branding
    SHOP_NAME: str = "Natimai"

    # OAuth 2.0 — Google
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # OAuth 2.0 — Microsoft
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_SECRET: str = ""
    MICROSOFT_TENANT_ID: str = "common"

    # OAuth callback base: public backend URL used to build the redirect_uri sent to providers.
    # Example: https://api.example.com
    OAUTH_REDIRECT_BASE_URL: str = ""

    # Frontend URL where the user is redirected after a successful/failed OAuth login.
    # Tokens are appended as query params: ?access_token=...&refresh_token=...
    FRONTEND_OAUTH_REDIRECT_URL: str = ""

    # ClamAV antivirus. When disabled the NoOpScanner marks every uploaded
    # document as clean — acceptable for local development only: the backend
    # refuses to start with CLAMAV_ENABLED=False outside ENVIRONMENT=local
    # (the compose and k8s manifests both set it to true).
    CLAMAV_ENABLED: bool = False
    CLAMAV_HOST: str = "clamav"
    CLAMAV_PORT: int = 3310
    CLAMAV_TIMEOUT_SECONDS: int = 30

    # PayZen Configuration
    PAYZEN_SITE_ID: str | None = None
    PAYZEN_API_PASSWORD_TEST: str | None = None
    PAYZEN_API_PASSWORD_PROD: str | None = None
    PAYZEN_PUBLIC_KEY_TEST: str | None = None
    PAYZEN_PUBLIC_KEY_PROD: str | None = None
    PAYZEN_MODE: Literal["TEST", "PRODUCTION"] = "TEST"
    PAYZEN_API_ENDPOINT: str = "https://api.osb.pf"
    # Deferred CB capture: when True, PayZen card payments are only AUTHORISED at
    # checkout (funds reserved, not debited) and CAPTURED later — typically at
    # shipment — via POST /admin/payments/{id}/capture or the ship action.
    # PayZen authorisations expire (~7 days): capture before then or re-authorise.
    PAYZEN_MANUAL_VALIDATION: bool = False
    # Reference (pivot) currency: the currency in which costs are normalized,
    # prices are computed and orders are billed. One per deployment. Override
    # per territory via the environment, never hardcode it in the code.
    REFERENCE_CURRENCY: str = "XPF"
    # Insurance rate applied on cost_in_reference before customs (CIF basis).
    # Expressed as a percentage (e.g. 1.0 = 1 %). Default 0 = no insurance.
    INSURANCE_RATE_PCT: float = 0.0
    PAYZEN_CURRENCY: str = "XPF"  # Default currency for French Polynesia
    PAYZEN_IPN_URL: str | None = None  # Will be computed based on backend URL
    PAYZEN_RETURN_URL: str | None = None  # Frontend URL to return after payment
    # Base URL for Payzen static assets (JS/CSS SmartForm SDK).
    PAYZEN_STATIC_URL: str = "https://static.osb.pf"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def payzen_ipn_url_computed(self) -> str:
        """Compute the PayZen IPN URL based on backend configuration."""
        if self.PAYZEN_IPN_URL:
            return self.PAYZEN_IPN_URL
        # Default to API endpoint + generic payments webhook
        backend_url = (
            str(self.BACKEND_CORS_ORIGINS[0])
            if self.BACKEND_CORS_ORIGINS
            else "http://localhost:8000"
        )
        return f"{backend_url}{self.API_V1_STR}/payments/webhooks/payzen"

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        """Check default secret."""
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    def _check_required_override(
        self, var_name: str, value: str, placeholder: str
    ) -> None:
        """Reject a still-placeholder value: warn in local, fail elsewhere.

        Makes the variable effectively mandatory in any non-local deployment.
        """
        if value.strip().lower() == placeholder.lower():
            message = (
                f"{var_name} is still the shipped placeholder '{placeholder}'. "
                f"Set a real value in your .env (required for any non-local deployment)."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    def _check_clamav_enabled(self) -> None:
        """Antivirus scanning of uploads is mandatory outside local.

        With CLAMAV_ENABLED=False the NoOpScanner declares every uploaded
        document clean, so payment documents would never be scanned.
        Warn in local development, refuse to start elsewhere.
        """
        if not self.CLAMAV_ENABLED:
            message = (
                "CLAMAV_ENABLED is False: uploaded documents are NOT scanned "
                "(the NoOpScanner marks everything clean). This is only "
                "acceptable in local development — set CLAMAV_ENABLED=true "
                "for any staging/production deployment."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        """Execute enforce non default secrets."""
        self._check_secret_key()
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )
        # The bootstrap admin account must be configured explicitly.
        self._check_required_override(
            "FIRST_SUPERUSER", self.FIRST_SUPERUSER, "admin@example.com"
        )
        self._check_clamav_enabled()

        return self


settings = Settings()
