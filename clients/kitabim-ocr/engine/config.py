from __future__ import annotations

import os
import platform
import sys
from typing import Literal

DEFAULT_OCR_ENGINE = "chandra"
SUPPORTED_OCR_ENGINES = ("chandra",)
OcrEngineName = Literal["chandra"]
DEFAULT_OCR_CONCURRENCY = 1
MAX_CHANDRA_CONCURRENCY = 4
DEFAULT_CHANDRA_METHOD = "hf"
DEFAULT_CHANDRA_MODEL_CHECKPOINT = "datalab-to/chandra-ocr-2"
DEFAULT_CHANDRA_PROMPT_TYPE = "ocr_layout"
SUPPORTED_CHANDRA_PROMPT_TYPES = ("ocr_layout", "ocr")
DEFAULT_CHANDRA_PROMPT_GUIDANCE = (
    "Input book pages are in Uyghur. All text must be accurately transcribed in "
    "modern Uyghur using Uyghur Arabic script verbatim, preserving diacritical marks "
    "and punctuation without translating or omitting text."
)
DEFAULT_CHANDRA_REPETITION_PENALTY: float = 1.05
DEFAULT_CHANDRA_MIN_IMAGE_DIM: int = 1536
DEFAULT_OCR_PAGE_TIMEOUT: float = 300.0
DEFAULT_OCR_MAX_RETRIES: int = 2
DEFAULT_OCR_PAGE_ZOOM_FACTOR: float = 3.0
DEFAULT_OCR_BLEED_THROUGH_SUPPRESSION: bool = True
DEFAULT_OCR_DOT_ENHANCEMENT: bool = True


def is_apple_silicon() -> bool:
    """Return True if running on macOS with Apple Silicon (ARM64)."""
    return sys.platform == "darwin" and platform.machine().lower() in (
        "arm64",
        "aarch64",
    )


def is_chandra_available() -> bool:
    """Return True if chandra package can be imported."""
    try:
        import chandra  # noqa: F401

        return True
    except ImportError:
        return False


def get_configured_engine(default: str = DEFAULT_OCR_ENGINE) -> str:
    """Read configured OCR engine name from environment variables.

    Checks KITABIM_OCR_ENGINE first, then OCR_ENGINE.
    Returns normalized lowercase engine name ('chandra').
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


def get_chandra_method(default: str = DEFAULT_CHANDRA_METHOD) -> str:
    """Read configured Chandra inference method ('hf' or 'vllm') from environment."""
    return (
        (
            os.environ.get("KITABIM_CHANDRA_METHOD")
            or os.environ.get("CHANDRA_METHOD")
            or default
        )
        .strip()
        .lower()
    )


def get_chandra_model_checkpoint(
    default: str = DEFAULT_CHANDRA_MODEL_CHECKPOINT,
) -> str:
    """Read configured Chandra model checkpoint from environment."""
    return (
        os.environ.get("KITABIM_CHANDRA_MODEL_CHECKPOINT")
        or os.environ.get("CHANDRA_MODEL_CHECKPOINT")
        or default
    ).strip()


def get_chandra_prompt_type(default: str = DEFAULT_CHANDRA_PROMPT_TYPE) -> str:
    """Read configured Chandra prompt type ('ocr_layout' or 'ocr') from environment."""
    val = (
        (
            os.environ.get("KITABIM_CHANDRA_PROMPT_TYPE")
            or os.environ.get("CHANDRA_PROMPT_TYPE")
            or default
        )
        .strip()
        .lower()
    )
    if val not in SUPPORTED_CHANDRA_PROMPT_TYPES:
        return default
    return val


def get_chandra_prompt_guidance(default: str = DEFAULT_CHANDRA_PROMPT_GUIDANCE) -> str:
    """Read configured Chandra language / script prompt guidance from environment.

    Returns the instruction string to prepend to the OCR prompt, or empty string if disabled.
    """
    raw = os.environ.get("KITABIM_CHANDRA_PROMPT_GUIDANCE") or os.environ.get(
        "CHANDRA_PROMPT_GUIDANCE"
    )
    if raw is None:
        return default
    val = raw.strip()
    if val.lower() in ("none", "false", "0", "disabled", "off"):
        return ""
    return val


def get_chandra_repetition_penalty(
    default: float = DEFAULT_CHANDRA_REPETITION_PENALTY,
) -> float:
    """Read configured repetition penalty for Chandra HF generation."""
    raw = os.environ.get("KITABIM_CHANDRA_REPETITION_PENALTY") or os.environ.get(
        "CHANDRA_REPETITION_PENALTY"
    )
    if raw is None or not str(raw).strip():
        return default
    try:
        val = float(str(raw).strip())
        return max(1.0, min(val, 2.0))
    except ValueError:
        return default


def get_chandra_min_image_dim(default: int = DEFAULT_CHANDRA_MIN_IMAGE_DIM) -> int:
    """Read configured minimum pixel dimension for Chandra image preprocessing."""
    raw = os.environ.get("KITABIM_CHANDRA_MIN_IMAGE_DIM") or os.environ.get(
        "CHANDRA_MIN_IMAGE_DIM"
    )
    if raw is None or not str(raw).strip():
        return default
    try:
        val = int(str(raw).strip())
        return max(512, val)
    except ValueError:
        return default


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

    An unset engine resolves to the configured default engine ('chandra').
    If requested is None, reads the configured value from the environment.
    Clamps to MAX_CHANDRA_CONCURRENCY for 'chandra'; floors at 1 otherwise.
    """
    resolved_engine = (engine or get_configured_engine()).strip().lower()
    max_limit = MAX_CHANDRA_CONCURRENCY if resolved_engine == "chandra" else None
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


def apply_surya_token_limits(*args, **kwargs) -> None:
    """Deprecated no-op retained for backwards compatibility."""
    pass


def is_bleed_through_suppression_enabled(
    default: bool = DEFAULT_OCR_BLEED_THROUGH_SUPPRESSION,
) -> bool:
    """Read whether bleed-through suppression preprocessing is enabled from environment."""
    raw = os.environ.get("KITABIM_OCR_BLEED_THROUGH_SUPPRESSION") or os.environ.get(
        "OCR_BLEED_THROUGH_SUPPRESSION"
    )
    if raw is None or not str(raw).strip():
        return default
    val = str(raw).strip().lower()
    return val not in ("false", "0", "no", "off", "disable", "disabled")


def get_configured_zoom_factor(
    default: float = DEFAULT_OCR_PAGE_ZOOM_FACTOR,
) -> float:
    """Read configured base PDF rendering zoom factor from environment variables.

    Checks KITABIM_OCR_ZOOM_FACTOR first, then OCR_PAGE_ZOOM_FACTOR.
    Clamped to range [1.5, 5.0].
    """
    raw = os.environ.get("KITABIM_OCR_ZOOM_FACTOR") or os.environ.get(
        "OCR_PAGE_ZOOM_FACTOR"
    )
    if raw is None or not str(raw).strip():
        return default
    try:
        val = float(str(raw).strip())
        return max(1.5, min(5.0, val))
    except ValueError:
        return default


def is_dot_enhancement_enabled(
    default: bool = DEFAULT_OCR_DOT_ENHANCEMENT,
) -> bool:
    """Read whether unsharp dot/contrast enhancement is enabled from environment."""
    raw = os.environ.get("KITABIM_OCR_DOT_ENHANCEMENT") or os.environ.get(
        "OCR_DOT_ENHANCEMENT"
    )
    if raw is None or not str(raw).strip():
        return default
    val = str(raw).strip().lower()
    return val not in ("false", "0", "no", "off", "disable", "disabled")
