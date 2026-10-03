import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

import engine.dictionary
from engine.dictionary import (
    fetch_and_cache_words,
    get_valid_words,
    load_cached_words,
)


@pytest.fixture(autouse=True)
def reset_memory_cache():
    engine.dictionary._MEMORY_WORDS = None
    yield
    engine.dictionary._MEMORY_WORDS = None


def test_load_cached_words_missing(tmp_path):
    missing_file = tmp_path / "nonexistent.txt"
    assert load_cached_words(missing_file) is None


def test_load_cached_words_success(tmp_path):
    cache_file = tmp_path / "words.txt"
    cache_file.write_text("سۆز1\nسۆز2\n\n  سۆز3  \n", encoding="utf-8")
    words = load_cached_words(cache_file)
    assert words == {"سۆز1", "سۆز2", "سۆز3"}


def test_fetch_and_cache_words_success(tmp_path):
    cache_file = tmp_path / "words.txt"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "كتاب\nمەكتەپ\nئوقۇغۇچى\n"

    with patch("engine.dictionary.httpx.get", return_value=mock_resp):
        words = fetch_and_cache_words(
            base_url="https://test.kitabim.ai/api",
            cache_path=cache_file,
        )

        assert words == {"كتاب", "مەكتەپ", "ئوقۇغۇچى"}
        assert cache_file.exists()
        assert cache_file.read_text(encoding="utf-8") == "كتاب\nمەكتەپ\nئوقۇغۇچى\n"


def test_get_valid_words_from_fresh_disk_cache(tmp_path):
    cache_file = tmp_path / "words.txt"
    cache_file.write_text("ئالما\nئانار\n", encoding="utf-8")

    # Should not make any HTTP call
    with patch("engine.dictionary.httpx.get") as mock_get:
        words = get_valid_words(
            base_url="https://test.kitabim.ai/api",
            cache_path=cache_file,
            force_refresh=False,
        )
        assert words == {"ئالما", "ئانار"}
        assert not mock_get.called


def test_get_valid_words_network_failure_falls_back_to_cache(tmp_path):
    cache_file = tmp_path / "words.txt"
    cache_file.write_text("قوغۇن\nتاۋۇز\n", encoding="utf-8")

    # Simulate stale cache
    old_time = time.time() - (8 * 86400)
    import os

    os.utime(cache_file, (old_time, old_time))

    with patch(
        "engine.dictionary.httpx.get", side_effect=httpx.ConnectError("offline")
    ):
        words = get_valid_words(
            base_url="https://test.kitabim.ai/api",
            cache_path=cache_file,
            force_refresh=True,
        )
        assert words == {"قوغۇن", "تاۋۇز"}
