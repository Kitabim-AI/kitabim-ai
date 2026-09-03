from __future__ import annotations

import os
import platform
import sys
from typing import Literal

DEFAULT_OCR_ENGINE = "surya"
SUPPORTED_OCR_ENGINES = ("surya", "savitr")
OcrEngineName = Literal["surya", "savitr"]


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
