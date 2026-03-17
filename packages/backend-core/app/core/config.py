from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv(override=True)

SERVICE_ROOT = Path(__file__).resolve().parents[2]
try:
    REPO_ROOT = SERVICE_ROOT.parents[1]
except IndexError:
    REPO_ROOT = SERVICE_ROOT


@dataclass(frozen=True)
class Settings:
    project_name: str = "Kitabim.AI"

    # API Keys / Models
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    # OCR, chat, categorization, and embedding models are ONLY configured
    # via the system_configs table. There are NO env-var or hardcoded fallbacks
    # for model names — if a key is missing from system_configs the call will
    # raise a RuntimeError so the misconfiguration is immediately visible.

    # Database
    database_url: str | None = os.getenv("DATABASE_URL")  # PostgreSQL connection string
    # Pool configuration (production-optimized)
    # Backend pool: Serves web requests (should have priority)
    # Worker pool: Background processing (limited to reserve connections for backend)
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "15"))
    # Worker-specific pool limits (smaller to reserve connections for backend)
    worker_db_pool_size: int = int(os.getenv("WORKER_DB_POOL_SIZE", "5"))
    worker_db_max_overflow: int = int(os.getenv("WORKER_DB_MAX_OVERFLOW", "10"))

    # Storage
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    gcs_data_bucket: str | None = os.getenv("GCS_DATA_BUCKET")
    gcs_media_bucket: str | None = os.getenv("GCS_MEDIA_BUCKET")

    # Directories
    data_dir: Path = Path(os.getenv("DATA_DIR", str(REPO_ROOT / "data")))
    uploads_dir: Path = data_dir / "uploads"
    covers_dir: Path = data_dir / "covers"

    # Parallel Processing
    max_parallel_pages: int = int(os.getenv("MAX_PARALLEL_PAGES", "4")) # OCR concurrency
    max_parallel_spell_check: int = int(os.getenv("MAX_PARALLEL_SPELL_CHECK", "6"))
    max_concurrent_spell_check_books: int = int(os.getenv("MAX_CONCURRENT_SPELL_CHECK_BOOKS", "3"))
    max_parallel_auto_correct: int = int(os.getenv("MAX_PARALLEL_AUTO_CORRECT", "10"))

    # Batch Sizes
    embed_batch_size: int = int(os.getenv("EMBED_BATCH_SIZE", "50"))

    # OCR Settings
    ocr_max_retries: int = int(os.getenv("OCR_MAX_RETRIES", "4"))

    # RAG Settings
    rag_score_threshold: float = float(os.getenv("RAG_SCORE_THRESHOLD", "0.50"))
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "16"))
    rag_max_chars_per_book: int = int(os.getenv("RAG_MAX_CHARS_PER_BOOK", "6000"))

    # Book Summary / Hierarchical RAG Settings
    summary_top_k: int = int(os.getenv("SUMMARY_TOP_K", "5"))
    summary_threshold: float = float(os.getenv("SUMMARY_THRESHOLD", "0.30"))
    summary_max_chars: int = int(os.getenv("SUMMARY_MAX_CHARS", "15000"))

    # Chunking Settings
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "100"))

    # LangChain / Observability
    langchain_cache_enabled: bool = os.getenv("LANGCHAIN_CACHE", "false").lower() == "true"
    langchain_tracing_enabled: bool = os.getenv("LANGCHAIN_TRACING", "false").lower() == "true"
    langchain_project: str | None = os.getenv("LANGCHAIN_PROJECT")
    rag_eval_enabled: bool = os.getenv("RAG_EVAL_ENABLED", "false").lower() == "true"

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "DEBUG")  # DEBUG, INFO, WARNING, ERROR

    # LLM Circuit Breaker
    llm_cb_failure_threshold: int = int(os.getenv("LLM_CB_FAILURE_THRESHOLD", "5"))
    llm_cb_recovery_seconds: int = int(os.getenv("LLM_CB_RECOVERY_SECONDS", "30"))
    llm_cb_half_open_max_calls: int = int(os.getenv("LLM_CB_HALF_OPEN_MAX_CALLS", "1"))
    llm_cb_cooling_period: int = int(os.getenv("LLM_CB_COOLING_PERIOD", "60"))  # Grace period after service restart (seconds)

    # Queue / Workers
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    queue_max_jobs: int = int(os.getenv("QUEUE_MAX_JOBS", "2"))
    queue_job_timeout: int = int(os.getenv("QUEUE_JOB_TIMEOUT", "7200"))
    maintenance_retention_days: int = int(os.getenv("MAINTENANCE_RETENTION_DAYS", "7"))

    # Pipeline Feature Flags
    enable_word_index: bool = os.getenv("ENABLE_WORD_INDEX", "true").lower() == "true"

    # Authentication / JWT
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_access_token_expire_minutes: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    jwt_refresh_token_expire_days: int = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # Google OAuth
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

    # Facebook OAuth
    facebook_client_id: str = os.getenv("FACEBOOK_CLIENT_ID", "")
    facebook_client_secret: str = os.getenv("FACEBOOK_CLIENT_SECRET", "")
    facebook_redirect_uri: str = os.getenv("FACEBOOK_REDIRECT_URI", "http://localhost:8000/api/auth/facebook/callback")

    # Twitter OAuth
    twitter_client_id: str = os.getenv("TWITTER_CLIENT_ID", "")
    twitter_client_secret: str = os.getenv("TWITTER_CLIENT_SECRET", "")
    twitter_redirect_uri: str = os.getenv("TWITTER_REDIRECT_URI", "http://localhost:8000/api/auth/twitter/callback")

    # Auth Behavior
    default_user_role: str = os.getenv("DEFAULT_USER_ROLE", "reader")
    admin_emails: str = os.getenv("ADMIN_EMAILS", "")  # Comma-separated list of admin emails

    # Cookie Security (set COOKIE_SECURE=false for local HTTP dev)
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"

    # CORS Settings - Allowed origins for API access
    cors_origins: str = os.getenv("CORS_ORIGINS", "https://kitabim.ai,https://www.kitabim.ai,http://localhost:3000,http://localhost:30080")

    # Environment (development, staging, production)
    environment: str = os.getenv("ENVIRONMENT", "development")

    # IP hashing salt (for privacy-compliant IP storage)
    ip_salt: str = os.getenv("IP_SALT", "")

    # Redis Cache
    redis_cache_enabled: bool = os.getenv("REDIS_CACHE_ENABLED", "true").lower() == "true"
    redis_cache_default_ttl: int = int(os.getenv("REDIS_CACHE_DEFAULT_TTL", "300"))
    redis_cache_key_prefix: str = os.getenv("REDIS_CACHE_KEY_PREFIX", "kitabim:cache:")

    # Per-feature TTLs (seconds)
    cache_ttl_books: int = int(os.getenv("CACHE_TTL_BOOKS", "900"))
    cache_ttl_system_config: int = int(os.getenv("CACHE_TTL_SYSTEM_CONFIG", "600"))
    cache_ttl_categories: int = int(os.getenv("CACHE_TTL_CATEGORIES", "900"))
    cache_ttl_rag_query: int = int(os.getenv("CACHE_TTL_RAG_QUERY", "3600"))
    cache_ttl_user_profile: int = int(os.getenv("CACHE_TTL_USER_PROFILE", "300"))
    cache_ttl_stats: int = int(os.getenv("CACHE_TTL_STATS", "120"))
    cache_ttl_summary_search: int = int(os.getenv("CACHE_TTL_SUMMARY_SEARCH", "1800"))
    cache_ttl_proverbs: int = int(os.getenv("CACHE_TTL_PROVERBS", "86400")) # 1 day by default

    # Cache behavior
    cache_skip_for_admins: bool = os.getenv("CACHE_SKIP_FOR_ADMINS", "true").lower() == "true"
    cache_max_keys_per_pattern: int = int(os.getenv("CACHE_MAX_KEYS_PER_PATTERN", "1000"))



settings = Settings()

# Ensure directories exist
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
settings.covers_dir.mkdir(parents=True, exist_ok=True)
