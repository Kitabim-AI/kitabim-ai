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
    gemini_model_name: str = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    gemini_categorization_model: str = os.getenv("GEMINI_CATEGORIZATION_MODEL", "gemini-3-flash-preview")
    gemini_embedding_model: str = os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")

    # Database
    mongodb_url: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name: str = os.getenv("MONGODB_DATABASE", "kitabim_ai_db")

    # Directories
    data_dir: Path = Path(os.getenv("DATA_DIR", str(REPO_ROOT / "data")))
    uploads_dir: Path = data_dir / "uploads"
    covers_dir: Path = data_dir / "covers"

    # Parallel Processing
    max_parallel_pages: int = int(os.getenv("MAX_PARALLEL_PAGES", "4"))

    # OCR Settings
    ocr_provider: str = os.getenv("OCR_PROVIDER", "gemini").lower()
    local_ocr_url: str = os.getenv("LOCAL_OCR_URL", "http://localhost:8001")
    ocr_max_retries: int = int(os.getenv("OCR_MAX_RETRIES", "4"))

    # RAG Settings
    rag_score_threshold: float = float(os.getenv("RAG_SCORE_THRESHOLD", "0.35"))
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "12"))
    rag_fallback_k: int = int(os.getenv("RAG_FALLBACK_K", "8"))
    rag_max_chars_per_book: int = int(os.getenv("RAG_MAX_CHARS_PER_BOOK", "4000"))

    # LangChain / Observability
    langchain_cache_enabled: bool = os.getenv("LANGCHAIN_CACHE", "false").lower() == "true"
    langchain_tracing_enabled: bool = os.getenv("LANGCHAIN_TRACING", "false").lower() == "true"
    langchain_project: str | None = os.getenv("LANGCHAIN_PROJECT")
    rag_eval_enabled: bool = os.getenv("RAG_EVAL_ENABLED", "false").lower() == "true"

    # LLM Circuit Breaker
    llm_cb_failure_threshold: int = int(os.getenv("LLM_CB_FAILURE_THRESHOLD", "5"))
    llm_cb_recovery_seconds: int = int(os.getenv("LLM_CB_RECOVERY_SECONDS", "30"))
    llm_cb_half_open_max_calls: int = int(os.getenv("LLM_CB_HALF_OPEN_MAX_CALLS", "1"))

    # Queue / Workers
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    queue_max_jobs: int = int(os.getenv("QUEUE_MAX_JOBS", "2"))
    queue_job_timeout: int = int(os.getenv("QUEUE_JOB_TIMEOUT", "1800"))
    queue_max_retries: int = int(os.getenv("QUEUE_MAX_RETRIES", "3"))
    job_lock_ttl_seconds: int = int(os.getenv("JOB_LOCK_TTL_SECONDS", "1800"))


settings = Settings()

# Ensure directories exist
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
settings.covers_dir.mkdir(parents=True, exist_ok=True)
