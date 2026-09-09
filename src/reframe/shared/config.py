"""
Reframe V7 Shared Configuration
Zero Paid Model Calls in default configuration.
"""
from typing import List, Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Environment
    ENVIRONMENT: str = "development"  # development, test, production
    DEBUG: bool = False
    PROJECT_NAME: str = "Reframe"
    API_V1_PREFIX: str = "/api/v1"

    # Security & Auth
    SECRET_KEY: str = "reframe-dev-secret-key-change-in-production-min32chars"
    SESSION_COOKIE_NAME: str = "reframe_session"
    SESSION_MAX_AGE_SECONDS: int = 86400 * 7  # 7 days
    SESSION_COOKIE_SECURE: bool = False  # False in development/test, True in production
    CSRF_SECRET: str = "reframe-csrf-secret-key-change-in-production"
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8000",
        "http://localhost:8001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8001"
    ]

    # Email Verification & Recovery Configuration
    AUTH_EMAIL_DELIVERY_MODE: str = "DEV_OUTBOX"  # DEV_OUTBOX, DISABLED, PROVIDER
    AUTH_CODE_HMAC_SECRET: str = "reframe-dev-auth-code-hmac-secret-min32chars"
    AUTH_CODE_TTL_SECONDS: int = 900  # 15 minutes
    AUTH_TICKET_TTL_SECONDS: int = 600  # 10 minutes
    AUTH_CODE_MAX_ATTEMPTS: int = 5
    AUTH_CODE_RESEND_COOLDOWN_SECONDS: int = 60

    # Google OIDC & Dev Auth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_OIDC_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/callback"
    AUTH_DEV_MODE: bool = False  # Strictly False by default; requires explicit enablement
    AUTH_DEMO_ACCOUNT_ENABLED: bool = False  # Explicitly public, non-admin preview account only
    AUTH_DEV_OUTBOX_VIEWER_ENABLED: bool = False  # Strictly False by default; enabled in demo/cert overlays
    SUBMISSION_READ_PROFILE_ENABLED: bool = True  # Submission evaluation profile: allows auth-free read for approved demo works
    REFRAME_PROFILE: str = "phase1_submission"
    PHASE1_SUBMISSION_PROFILE_ENABLED: bool = True  # Explicit Phase 1 Profile (Single public author + decoupled browser journey)
    BROWSER_SESSION_COOKIE_NAME: str = "reframe_viewer_session"
    BROWSER_SESSION_MAX_AGE_SECONDS: int = 2592000  # 30 days
    AUTH_EMAIL_VERIFICATION_MAX_REQUESTS: int = 5
    AUTH_EMAIL_VERIFICATION_WINDOW_SECONDS: int = 60

    # Databases
    SCHEMA_INIT_MODE: str = "AUTO"  # AUTO, MIGRATIONS_ONLY, CREATE_ALL
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/phase1_submission.db"
    SYNC_DATABASE_URL: str = "sqlite:///./data/phase1_submission.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: str = ""
    CLICKHOUSE_DATABASE: str = "reframe"
    CLICKHOUSE_ALLOW_WRITE_ACCESS: bool = False  # Runtime identity is STRICTLY read-only

    @model_validator(mode="after")
    def validate_database_isolation(self) -> "Settings":
        """Strictly prevents running Phase 1 submission profile against the original reframe_v7.db across all execution paths."""
        if getattr(self, "PHASE1_SUBMISSION_PROFILE_ENABLED", False) or getattr(self, "REFRAME_PROFILE", "") == "phase1_submission":
            for field_name in ("DATABASE_URL", "SYNC_DATABASE_URL"):
                raw_url = getattr(self, field_name, "") or ""
                clean_url = raw_url.lower().replace("\\", "/")
                if "reframe_v7.db" in clean_url:
                    raise ValueError(
                        f"ISOLATION_VIOLATION: Phase 1 submission profile cannot execute against original "
                        f"reframe_v7.db database in {field_name}. Please configure an isolated database path (e.g. ./data/phase1_submission.db)."
                    )
        return self

    # Storage
    STORAGE_BACKEND: str = "local"  # local or gcs
    GCS_BUCKET_NAME: Optional[str] = None
    LOCAL_STORAGE_DIR: str = "./data/storage"

    # AI, Cost & Google Gemini Budget Controls (Cost Emergency Guardrails - R2-08)
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL_ID: str = "gemini-3.6-flash"  # Target approved Gemini model
    GEMINI_MODEL: str = "gemini-3.6-flash"     # Alias for compatibility
    GEMINI_MAX_OUTPUT_TOKENS: int = 4096
    GEMINI_TEMPERATURE: float = 0.2
    MAX_MODEL_CALLS_PER_ANALYSIS_RUN: int = 1  # Strictly 1 call per run (Section 53)

    # Mandatory Zero-Cost Default Flags (R2-08 / R2-09 / R3-04)
    EXECUTION_MODE: str = "OFFLINE_FIXTURE"  # OFFLINE_FIXTURE or LIVE_GOOGLE
    PAID_CALLS_ENABLED: bool = False
    # Independent comment-only capability; the global emergency kill switch still applies.
    COMMENT_MODERATION_ENABLED: bool = False
    COMMENT_MODERATION_API_KEY: Optional[str] = None
    SPEND_KILL_SWITCH_ACTIVE: bool = True
    LIVE_AGENT_ENABLED: bool = False
    LIVE_EVAL_ENABLED: bool = False
    LEGACY_PAID_PATH_ENABLED: bool = False
    ADMIN_COST_UNLOCK: Optional[str] = None

    # Hard Budget Ceilings (in Micros: 1 USD = 1,000,000 micros) (R2-08)
    PUBLIC_REFRAME_MODEL_CALLS: int = 0
    PUBLIC_PROOF_LOOKUP_MODEL_CALLS: int = 0
    PUBLIC_COMMUNITY_MODEL_CALLS: int = 0
    ADMIN_REFRESH_MAX_CALLS: int = 3
    THEORY_MAX_CALLS: int = 2
    MAX_CONCURRENT_PAID_RUNS: int = 1
    MAX_BUDGET_MICROS_PER_RUN: int = 500_000      # $0.50 max per run
    DAILY_BUDGET_MICROS: int = 1_000_000          # $1.00 max daily project budget (R2-08)
    USER_DAILY_BUDGET_MICROS: int = 1_000_000     # $1.00 max daily per user
    CAMPAIGN_BUDGET_MICROS: int = 1_000_000       # $1.00 max campaign cumulative ceiling (RC-07)
    CAMPAIGN_FREEZE_MICROS: int = 800_000         # $0.80 campaign new invocation freeze threshold (RC-07)
    FINAL_VALIDATION_TOTAL_BUDGET_USD: float = 5.00

    # Worker & Leases
    EMBEDDED_WORKER_ENABLED: bool = False  # Strictly False by default; container worker is sole processor
    WORKER_LEASE_SECONDS: int = 30
    WORKER_POLL_INTERVAL_SECONDS: float = 1.0
    IDEMPOTENCY_EXPIRY_SECONDS: int = 86400

    # Feature Flags for Synthetic Audience Lab & Demo Content (Section 46)
    ENABLE_AUDIENCE_LAB: bool = False  # Strictly False by default; enabled in demo/cert overlays
    ENABLE_SYNTHETIC_DEMO_CONTENT: bool = False  # Strictly False by default; enabled in demo/cert overlays
    ENABLE_SYNTHETIC_MAGAZINE: bool = False  # Strictly False by default; enabled in demo/cert overlays or explicit env


    # Simulation Settings
    SIMULATION_SALT: str = "reframe-usa-audience-salt-2026-v7"
    SIMULATION_DATA_DIR: str = "./data/simulation"
    NEMOTRON_DATASET_ID: str = "nvidia/Nemotron-Personas-USA"
    NEMOTRON_DATASET_REVISION: str = "5b4cd35ab46490c1da1bd2b5a2324d6f871be180"

    # Dataset pinning
    DEFAULT_DATASET_VERSION: str = "v3"
    DEFAULT_EDITION_ID: str = "tbw-fullscreen-archive"
    CANONICAL_ASSET_SHA256: str = "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"

    def validate_production_settings(self) -> None:
        """Enforces fail-fast production invariants."""
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == "reframe-dev-secret-key-change-in-production-min32chars":
                raise RuntimeError("Production startup blocked: Insecure default SECRET_KEY detected.")
            if self.CSRF_SECRET == "reframe-csrf-secret-key-change-in-production":
                raise RuntimeError("Production startup blocked: Insecure default CSRF_SECRET detected.")
            if self.AUTH_CODE_HMAC_SECRET == "reframe-dev-auth-code-hmac-secret-min32chars" or len(self.AUTH_CODE_HMAC_SECRET) < 32:
                raise RuntimeError("Production startup blocked: Insecure default or short AUTH_CODE_HMAC_SECRET detected.")
            if self.AUTH_EMAIL_DELIVERY_MODE == "DEV_OUTBOX":
                raise RuntimeError("Production startup blocked: AUTH_EMAIL_DELIVERY_MODE cannot be DEV_OUTBOX in production.")
            if self.AUTH_DEV_OUTBOX_VIEWER_ENABLED:
                raise RuntimeError("Production startup blocked: AUTH_DEV_OUTBOX_VIEWER_ENABLED must be False in production.")
            if not self.SESSION_COOKIE_SECURE:
                raise RuntimeError("Production startup blocked: SESSION_COOKIE_SECURE must be True in production.")
            if self.AUTH_DEV_MODE:
                raise RuntimeError("Production startup blocked: AUTH_DEV_MODE must be False in production.")
            if self.STORAGE_BACKEND == "gcs" and not self.GCS_BUCKET_NAME:
                raise RuntimeError("Production startup blocked: GCS_BUCKET_NAME must be set when STORAGE_BACKEND=gcs.")



settings = Settings()

