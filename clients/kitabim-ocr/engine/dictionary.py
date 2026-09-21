from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import httpx

logger = logging.getLogger("kitabim_ocr_client.engine.dictionary")

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "kitabim-ocr"
WORDS_CACHE_FILE = DEFAULT_CACHE_DIR / "words_dict.txt"
CACHE_TTL_SECONDS = 7 * 86400  # 7 days

_MEMORY_WORDS: set[str] | None = None


def get_default_words_cache_path() -> Path:
    cache_dir = os.environ.get("KITABIM_CACHE_DIR")
    if cache_dir:
        return Path(cache_dir).expanduser() / "words_dict.txt"
    return WORDS_CACHE_FILE


def fetch_and_cache_words(
    base_url: str | None = None,
    cache_path: Path | None = None,
    timeout: float = 15.0,
) -> set[str]:
    """Fetch words bundle from Kitabim API and cache to disk."""
    dest = cache_path or get_default_words_cache_path()
    raw_base = (
        base_url or os.environ.get("KITABIM_BASE_URL") or "https://kitabim.ai/api"
    ).rstrip("/")

    if raw_base.endswith("/api"):
        url = f"{raw_base}/dictionary/words-bundle"
    else:
        url = f"{raw_base}/api/dictionary/words-bundle"

    logger.info("Fetching words bundle from %s...", url)
    headers = {}
    app_id = os.environ.get("SECURITY_APP_ID")
    if app_id:
        headers["X-Kitabim-App-Id"] = app_id

    response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch words bundle: {response.status_code} {response.text[:200]}"
        )

    words_text = response.text
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_file = dest.with_suffix(".tmp")
    temp_file.write_text(words_text, encoding="utf-8")
    temp_file.replace(dest)

    words = {line.strip() for line in words_text.splitlines() if line.strip()}
    logger.info("Cached %d dictionary words to %s", len(words), dest)
    return words


def load_cached_words(cache_path: Path | None = None) -> set[str] | None:
    """Load words from local cache file if it exists."""
    dest = cache_path or get_default_words_cache_path()
    if not dest.exists():
        return None
    try:
        content = dest.read_text(encoding="utf-8")
        words = {line.strip() for line in content.splitlines() if line.strip()}
        return words
    except Exception as exc:
        logger.warning("Failed to read words cache at %s: %s", dest, exc)
        return None


def get_valid_words(
    base_url: str | None = None,
    cache_path: Path | None = None,
    force_refresh: bool = False,
    timeout: float = 15.0,
) -> set[str]:
    """Get valid words set, using in-memory cache, disk cache, or remote API."""
    global _MEMORY_WORDS
    if _MEMORY_WORDS is not None and not force_refresh:
        return _MEMORY_WORDS

    dest = cache_path or get_default_words_cache_path()
    is_stale = True
    if dest.exists():
        age = time.time() - os.path.getmtime(dest)
        if age < CACHE_TTL_SECONDS:
            is_stale = False

    if not force_refresh and not is_stale:
        cached = load_cached_words(dest)
        if cached is not None:
            _MEMORY_WORDS = cached
            return cached

    # Stale, missing, or force_refresh -> try fetching
    try:
        words = fetch_and_cache_words(
            base_url=base_url, cache_path=dest, timeout=timeout
        )
        _MEMORY_WORDS = words
        return words
    except Exception as exc:
        logger.warning(
            "Could not refresh words bundle from remote API (%s). Falling back to existing cache.",
            exc,
        )
        cached = load_cached_words(dest)
        if cached is not None:
            _MEMORY_WORDS = cached
            return cached
        logger.warning(
            "No words dictionary cache available. De-hyphenation will be bypassed."
        )
        _MEMORY_WORDS = set()
        return _MEMORY_WORDS
