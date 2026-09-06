from __future__ import annotations

import os
import platform
import sys
from typing import Literal

DEFAULT_OCR_ENGINE = "surya"
SUPPORTED_OCR_ENGINES = ("surya", "savitr")
OcrEngineName = Literal["surya", "savitr"]
DEFAULT_OCR_CONCURRENCY = 4
MAX_SURYA_CONCURRENCY = 4
DEFAULT_OCR_PAGE_TIMEOUT: float = 120.0
DEFAULT_OCR_MAX_RETRIES: int = 2
DEFAULT_SURYA_MAX_TOKENS_FULL_PAGE: int = 2500


def is_apple_silicon() -> bool:
    """Return True if running on macOS with Apple Silicon (ARM64)."""
    return sys.platform == "darwin" and platform.machine().lower() in (
        "arm64",
        "aarch64",
    )


def is_savitr_available() -> bool:
    """Return True if savitr or mlx-vlm dependencies can be imported."""
    try:
        import mlx_vlm  # noqa: F401

        return True
    except ImportError:
        try:
            import savitr  # noqa: F401

            return True
        except ImportError:
            return False


def get_configured_engine(default: str = DEFAULT_OCR_ENGINE) -> str:
    """Read configured OCR engine name from environment variables.

    Checks KITABIM_OCR_ENGINE first, then OCR_ENGINE.
    Returns normalized lowercase engine name ('surya' or 'savitr').
    """
    engine = (
        (
            os.environ.get("KITABIM_OCR_ENGINE")
            or os.environ.get("OCR_ENGINE")
            or default
        )
        .strip()
        .lower()
    )

    if engine not in SUPPORTED_OCR_ENGINES:
        raise ValueError(
            f"Unsupported OCR engine '{engine}'. Supported engines: {', '.join(SUPPORTED_OCR_ENGINES)}"
        )
    return engine


def get_savitr_model_path() -> str | None:
    """Read optional custom Savitr model path from environment variables."""
    return (
        os.environ.get("SAVITR_MODEL_PATH")
        or os.environ.get("SAVITR_BASE_PATH")
        or None
    )


def get_configured_concurrency(
    default: int = DEFAULT_OCR_CONCURRENCY,
    max_limit: int | None = None,
) -> int:
    """Read configured OCR concurrency from environment variables.

    Checks KITABIM_OCR_CONCURRENCY first, then OCR_CONCURRENCY.
    Returns an integer >= 1 (1 indicates concurrent processing is disabled).
    If max_limit is provided, clamps the return value to at most max_limit.
    """
    raw = os.environ.get("KITABIM_OCR_CONCURRENCY") or os.environ.get("OCR_CONCURRENCY")
    if raw is None or not str(raw).strip():
        val = default
    else:
        try:
            val = int(str(raw).strip())
        except ValueError:
            val = default
    val = max(1, val)
    if max_limit is not None:
        val = min(val, max(1, max_limit))
    return val


def resolve_concurrency(engine: str | None, requested: int | None = None) -> int:
    """Resolve the OCR concurrency to use for a given engine.

    An unset engine resolves to the configured default engine, matching
    get_recognition_predictor's own `engine or get_configured_engine()`
    resolution, so callers that don't know the active engine yet (e.g. the
    standalone preview server) clamp consistently with the rest of the app.

    If requested is None, reads the configured value from the environment.
    Clamps to MAX_SURYA_CONCURRENCY for the 'surya' engine; floors at 1
    otherwise.
    """
    resolved_engine = (engine or get_configured_engine()).strip().lower()
    max_limit = MAX_SURYA_CONCURRENCY if resolved_engine == "surya" else None
    if requested is None:
        return get_configured_concurrency(max_limit=max_limit)
    val = max(1, requested)
    if max_limit is not None:
        val = min(val, max_limit)
    return val


def get_configured_page_timeout(
    default: float | None = DEFAULT_OCR_PAGE_TIMEOUT,
) -> float | None:
    """Read configured per-page OCR timeout in seconds from environment variables.

    Checks KITABIM_OCR_PAGE_TIMEOUT first, then OCR_PAGE_TIMEOUT.
    Returns a positive float in seconds, or None if disabled (e.g. '0', 'none', 'false').
    """
    raw = os.environ.get("KITABIM_OCR_PAGE_TIMEOUT") or os.environ.get(
        "OCR_PAGE_TIMEOUT"
    )
    if raw is None or not str(raw).strip():
        return default
    raw_str = str(raw).strip().lower()
    if raw_str in ("none", "null", "false", "0", "0.0", "-1"):
        return None
    try:
        val = float(raw_str)
        return val if val > 0 else None
    except ValueError:
        return default


def get_configured_max_retries(
    default: int = DEFAULT_OCR_MAX_RETRIES,
) -> int:
    """Read configured max OCR retry attempts per page from environment variables.

    Checks KITABIM_OCR_MAX_RETRIES first, then OCR_MAX_RETRIES.
    Returns an integer >= 1 (1 means single attempt with no retries).
    """
    raw = os.environ.get("KITABIM_OCR_MAX_RETRIES") or os.environ.get("OCR_MAX_RETRIES")
    if raw is None or not str(raw).strip():
        return default
    try:
        val = int(str(raw).strip())
        return max(1, val)
    except ValueError:
        return default


def apply_surya_token_limits(
    default_max_tokens: int = DEFAULT_SURYA_MAX_TOKENS_FULL_PAGE,
) -> None:
    """Ensure SURYA_MAX_TOKENS_FULL_PAGE is capped to a sane limit if not explicitly set."""
    if "SURYA_MAX_TOKENS_FULL_PAGE" not in os.environ:
        custom_limit = os.environ.get("KITABIM_OCR_MAX_TOKENS")
        if custom_limit and custom_limit.strip():
            os.environ["SURYA_MAX_TOKENS_FULL_PAGE"] = custom_limit.strip()
        else:
            os.environ["SURYA_MAX_TOKENS_FULL_PAGE"] = str(default_max_tokens)
