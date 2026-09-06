import pytest

from engine.config import (
    DEFAULT_OCR_CONCURRENCY,
    DEFAULT_OCR_ENGINE,
    DEFAULT_OCR_MAX_RETRIES,
    DEFAULT_OCR_PAGE_TIMEOUT,
    DEFAULT_SURYA_MAX_TOKENS_FULL_PAGE,
    MAX_SURYA_CONCURRENCY,
    apply_surya_token_limits,
    get_configured_concurrency,
    get_configured_engine,
    get_configured_max_retries,
    get_configured_page_timeout,
    get_savitr_model_path,
    is_apple_silicon,
    is_savitr_available,
    resolve_concurrency,
)


def test_get_configured_engine_defaults_to_surya(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_ENGINE", raising=False)
    monkeypatch.delenv("OCR_ENGINE", raising=False)
    assert get_configured_engine() == DEFAULT_OCR_ENGINE
    assert get_configured_engine() == "surya"


def test_get_configured_engine_from_kitabim_ocr_engine_env(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "savitr")
    monkeypatch.delenv("OCR_ENGINE", raising=False)
    assert get_configured_engine() == "savitr"


def test_get_configured_engine_from_ocr_engine_env(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_ENGINE", raising=False)
    monkeypatch.setenv("OCR_ENGINE", "SAVITR")
    assert get_configured_engine() == "savitr"


def test_get_configured_engine_kitabim_takes_precedence(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "surya")
    monkeypatch.setenv("OCR_ENGINE", "savitr")
    assert get_configured_engine() == "surya"


def test_get_configured_engine_invalid_raises_value_error(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "unsupported_engine")
    with pytest.raises(ValueError, match="Unsupported OCR engine"):
        get_configured_engine()


def test_get_savitr_model_path(monkeypatch):
    monkeypatch.delenv("SAVITR_MODEL_PATH", raising=False)
    monkeypatch.delenv("SAVITR_BASE_PATH", raising=False)
    assert get_savitr_model_path() is None

    monkeypatch.setenv("SAVITR_MODEL_PATH", "/custom/path/model")
    assert get_savitr_model_path() == "/custom/path/model"

    monkeypatch.delenv("SAVITR_MODEL_PATH", raising=False)
    monkeypatch.setenv("SAVITR_BASE_PATH", "/base/path/model")
    assert get_savitr_model_path() == "/base/path/model"


def test_is_apple_silicon_bool():
    result = is_apple_silicon()
    assert isinstance(result, bool)


def test_is_savitr_available_bool():
    result = is_savitr_available()
    assert isinstance(result, bool)


def test_get_configured_concurrency_defaults_to_four(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_CONCURRENCY", raising=False)
    monkeypatch.delenv("OCR_CONCURRENCY", raising=False)
    assert get_configured_concurrency() == DEFAULT_OCR_CONCURRENCY
    assert get_configured_concurrency() == 4


def test_get_configured_concurrency_from_kitabim_env(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "2")
    monkeypatch.delenv("OCR_CONCURRENCY", raising=False)
    assert get_configured_concurrency() == 2


def test_get_configured_concurrency_from_ocr_concurrency_env(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_CONCURRENCY", raising=False)
    monkeypatch.setenv("OCR_CONCURRENCY", "2")
    assert get_configured_concurrency() == 2


def test_get_configured_concurrency_kitabim_takes_precedence(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "3")
    monkeypatch.setenv("OCR_CONCURRENCY", "6")
    assert get_configured_concurrency() == 3


def test_get_configured_concurrency_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "invalid")
    assert get_configured_concurrency(default=2) == 2


def test_get_configured_concurrency_zero_or_negative_clamped_to_one(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "0")
    assert get_configured_concurrency() == 1
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "-5")
    assert get_configured_concurrency() == 1


def test_get_configured_concurrency_max_limit_clamped(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "16")
    assert get_configured_concurrency(max_limit=4) == 4
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "2")
    assert get_configured_concurrency(max_limit=4) == 2


def test_resolve_concurrency_clamps_surya_to_max(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_CONCURRENCY", raising=False)
    assert resolve_concurrency("surya", 16) == MAX_SURYA_CONCURRENCY
    assert resolve_concurrency("surya", 2) == 2


def test_resolve_concurrency_floors_non_surya_at_one_without_capping(monkeypatch):
    assert resolve_concurrency("savitr", 16) == 16
    assert resolve_concurrency("savitr", -3) == 1


def test_resolve_concurrency_blank_engine_resolves_to_configured_default(monkeypatch):
    # A blank/unset engine (e.g. a caller that hasn't tracked one) must clamp
    # the same way as the actually configured default engine, not silently
    # assume 'surya' or skip clamping — this matches
    # get_recognition_predictor's own `engine or get_configured_engine()`.
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "savitr")
    assert resolve_concurrency(None, 16) == 16
    assert resolve_concurrency("", 16) == 16

    monkeypatch.setenv("KITABIM_OCR_ENGINE", "surya")
    assert resolve_concurrency(None, 16) == MAX_SURYA_CONCURRENCY


def test_resolve_concurrency_reads_env_when_requested_is_none(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "16")
    assert resolve_concurrency("surya", None) == MAX_SURYA_CONCURRENCY
    assert resolve_concurrency("savitr", None) == 16


def test_get_configured_page_timeout_defaults_to_120(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_PAGE_TIMEOUT", raising=False)
    monkeypatch.delenv("OCR_PAGE_TIMEOUT", raising=False)
    assert get_configured_page_timeout() == DEFAULT_OCR_PAGE_TIMEOUT
    assert get_configured_page_timeout() == 120.0


def test_get_configured_page_timeout_from_env(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_PAGE_TIMEOUT", "90")
    monkeypatch.delenv("OCR_PAGE_TIMEOUT", raising=False)
    assert get_configured_page_timeout() == 90.0

    monkeypatch.delenv("KITABIM_OCR_PAGE_TIMEOUT", raising=False)
    monkeypatch.setenv("OCR_PAGE_TIMEOUT", "60.5")
    assert get_configured_page_timeout() == 60.5


def test_get_configured_page_timeout_precedence(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_PAGE_TIMEOUT", "45")
    monkeypatch.setenv("OCR_PAGE_TIMEOUT", "90")
    assert get_configured_page_timeout() == 45.0


def test_get_configured_page_timeout_disabled_values(monkeypatch):
    for disabled_val in ("0", "0.0", "-1", "none", "null", "false"):
        monkeypatch.setenv("KITABIM_OCR_PAGE_TIMEOUT", disabled_val)
        assert get_configured_page_timeout() is None


def test_get_configured_page_timeout_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_PAGE_TIMEOUT", "invalid_number")
    assert get_configured_page_timeout(default=100.0) == 100.0


def test_get_configured_max_retries_defaults_to_two(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_MAX_RETRIES", raising=False)
    monkeypatch.delenv("OCR_MAX_RETRIES", raising=False)
    assert get_configured_max_retries() == DEFAULT_OCR_MAX_RETRIES
    assert get_configured_max_retries() == 2


def test_get_configured_max_retries_from_env(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_MAX_RETRIES", "3")
    monkeypatch.delenv("OCR_MAX_RETRIES", raising=False)
    assert get_configured_max_retries() == 3

    monkeypatch.delenv("KITABIM_OCR_MAX_RETRIES", raising=False)
    monkeypatch.setenv("OCR_MAX_RETRIES", "1")
    assert get_configured_max_retries() == 1


def test_get_configured_max_retries_clamped_to_one(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_MAX_RETRIES", "0")
    assert get_configured_max_retries() == 1
    monkeypatch.setenv("KITABIM_OCR_MAX_RETRIES", "-2")
    assert get_configured_max_retries() == 1


def test_apply_surya_token_limits(monkeypatch):
    import os

    monkeypatch.delenv("SURYA_MAX_TOKENS_FULL_PAGE", raising=False)
    monkeypatch.delenv("KITABIM_OCR_MAX_TOKENS", raising=False)
    apply_surya_token_limits()
    assert os.environ["SURYA_MAX_TOKENS_FULL_PAGE"] == str(
        DEFAULT_SURYA_MAX_TOKENS_FULL_PAGE
    )

    # Respects custom KITABIM_OCR_MAX_TOKENS
    monkeypatch.delenv("SURYA_MAX_TOKENS_FULL_PAGE", raising=False)
    monkeypatch.setenv("KITABIM_OCR_MAX_TOKENS", "1800")
    apply_surya_token_limits()
    assert os.environ["SURYA_MAX_TOKENS_FULL_PAGE"] == "1800"

    # Does not overwrite existing SURYA_MAX_TOKENS_FULL_PAGE
    monkeypatch.setenv("SURYA_MAX_TOKENS_FULL_PAGE", "4096")
    apply_surya_token_limits()
    assert os.environ["SURYA_MAX_TOKENS_FULL_PAGE"] == "4096"
