import pytest

from engine.config import (
    DEFAULT_CHANDRA_METHOD,
    DEFAULT_CHANDRA_MODEL_CHECKPOINT,
    DEFAULT_CHANDRA_MIN_IMAGE_DIM,
    DEFAULT_CHANDRA_PROMPT_GUIDANCE,
    DEFAULT_CHANDRA_PROMPT_TYPE,
    DEFAULT_CHANDRA_REPETITION_PENALTY,
    DEFAULT_OCR_BLEED_THROUGH_SUPPRESSION,
    DEFAULT_OCR_CONCURRENCY,
    DEFAULT_OCR_DOT_ENHANCEMENT,
    DEFAULT_OCR_ENGINE,
    DEFAULT_OCR_MAX_RETRIES,
    DEFAULT_OCR_PAGE_TIMEOUT,
    DEFAULT_OCR_PAGE_ZOOM_FACTOR,
    MAX_CHANDRA_CONCURRENCY,
    apply_surya_token_limits,
    get_chandra_method,
    get_chandra_min_image_dim,
    get_chandra_model_checkpoint,
    get_chandra_prompt_guidance,
    get_chandra_prompt_type,
    get_chandra_repetition_penalty,
    get_configured_concurrency,
    get_configured_engine,
    get_configured_max_retries,
    get_configured_page_timeout,
    get_configured_zoom_factor,
    is_apple_silicon,
    is_bleed_through_suppression_enabled,
    is_chandra_available,
    is_dot_enhancement_enabled,
    resolve_concurrency,
)


def test_get_configured_engine_defaults_to_chandra(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_ENGINE", raising=False)
    monkeypatch.delenv("OCR_ENGINE", raising=False)
    assert get_configured_engine() == DEFAULT_OCR_ENGINE
    assert get_configured_engine() == "chandra"


def test_get_configured_engine_from_kitabim_ocr_engine_env(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "chandra")
    monkeypatch.delenv("OCR_ENGINE", raising=False)
    assert get_configured_engine() == "chandra"


def test_get_configured_engine_from_ocr_engine_env(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_ENGINE", raising=False)
    monkeypatch.setenv("OCR_ENGINE", "CHANDRA")
    assert get_configured_engine() == "chandra"


def test_get_configured_engine_kitabim_takes_precedence(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "chandra")
    monkeypatch.setenv("OCR_ENGINE", "other")
    assert get_configured_engine() == "chandra"


def test_get_configured_engine_invalid_raises_value_error(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "unsupported_engine")
    with pytest.raises(ValueError, match="Unsupported OCR engine"):
        get_configured_engine()


def test_get_chandra_method(monkeypatch):
    monkeypatch.delenv("KITABIM_CHANDRA_METHOD", raising=False)
    monkeypatch.delenv("CHANDRA_METHOD", raising=False)
    assert get_chandra_method() == DEFAULT_CHANDRA_METHOD
    assert get_chandra_method() == "hf"

    monkeypatch.setenv("KITABIM_CHANDRA_METHOD", "vllm")
    assert get_chandra_method() == "vllm"

    monkeypatch.delenv("KITABIM_CHANDRA_METHOD", raising=False)
    monkeypatch.setenv("CHANDRA_METHOD", "hf")
    assert get_chandra_method() == "hf"


def test_get_chandra_model_checkpoint(monkeypatch):
    monkeypatch.delenv("KITABIM_CHANDRA_MODEL_CHECKPOINT", raising=False)
    monkeypatch.delenv("CHANDRA_MODEL_CHECKPOINT", raising=False)
    assert get_chandra_model_checkpoint() == DEFAULT_CHANDRA_MODEL_CHECKPOINT

    monkeypatch.setenv("KITABIM_CHANDRA_MODEL_CHECKPOINT", "custom/chandra-model")
    assert get_chandra_model_checkpoint() == "custom/chandra-model"


def test_is_apple_silicon_bool():
    result = is_apple_silicon()
    assert isinstance(result, bool)


def test_is_chandra_available_bool():
    result = is_chandra_available()
    assert isinstance(result, bool)


def test_get_configured_concurrency_defaults_to_one(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_CONCURRENCY", raising=False)
    monkeypatch.delenv("OCR_CONCURRENCY", raising=False)
    assert get_configured_concurrency() == DEFAULT_OCR_CONCURRENCY
    assert get_configured_concurrency() == 1


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


def test_resolve_concurrency_clamps_chandra_to_max(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_CONCURRENCY", raising=False)
    assert resolve_concurrency("chandra", 16) == MAX_CHANDRA_CONCURRENCY
    assert resolve_concurrency("chandra", 2) == 2


def test_resolve_concurrency_blank_engine_resolves_to_configured_default(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "chandra")
    assert resolve_concurrency(None, 16) == MAX_CHANDRA_CONCURRENCY
    assert resolve_concurrency("", 16) == MAX_CHANDRA_CONCURRENCY


def test_resolve_concurrency_reads_env_when_requested_is_none(monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "16")
    assert resolve_concurrency("chandra", None) == MAX_CHANDRA_CONCURRENCY


def test_get_configured_page_timeout_defaults_to_300(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_PAGE_TIMEOUT", raising=False)
    monkeypatch.delenv("OCR_PAGE_TIMEOUT", raising=False)
    assert get_configured_page_timeout() == DEFAULT_OCR_PAGE_TIMEOUT
    assert get_configured_page_timeout() == 300.0


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


def test_apply_surya_token_limits_noop():
    # Should not raise
    apply_surya_token_limits()


def test_is_bleed_through_suppression_enabled_defaults_to_true(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_BLEED_THROUGH_SUPPRESSION", raising=False)
    monkeypatch.delenv("OCR_BLEED_THROUGH_SUPPRESSION", raising=False)
    assert DEFAULT_OCR_BLEED_THROUGH_SUPPRESSION is True
    assert is_bleed_through_suppression_enabled() is True


def test_is_bleed_through_suppression_enabled_env_override(monkeypatch):
    for disabled_val in ("false", "0", "no", "off", "disable", "disabled", "FALSE"):
        monkeypatch.setenv("KITABIM_OCR_BLEED_THROUGH_SUPPRESSION", disabled_val)
        assert is_bleed_through_suppression_enabled() is False

    for enabled_val in ("true", "1", "yes", "on", "enable", "TRUE"):
        monkeypatch.setenv("KITABIM_OCR_BLEED_THROUGH_SUPPRESSION", enabled_val)
        assert is_bleed_through_suppression_enabled() is True

    # Fallback to OCR_BLEED_THROUGH_SUPPRESSION
    monkeypatch.delenv("KITABIM_OCR_BLEED_THROUGH_SUPPRESSION", raising=False)
    monkeypatch.setenv("OCR_BLEED_THROUGH_SUPPRESSION", "false")
    assert is_bleed_through_suppression_enabled() is False


def test_get_configured_zoom_factor(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_ZOOM_FACTOR", raising=False)
    monkeypatch.delenv("OCR_PAGE_ZOOM_FACTOR", raising=False)
    assert get_configured_zoom_factor() == DEFAULT_OCR_PAGE_ZOOM_FACTOR
    assert get_configured_zoom_factor() == 3.0

    # Custom valid float
    monkeypatch.setenv("KITABIM_OCR_ZOOM_FACTOR", "3.5")
    assert get_configured_zoom_factor() == 3.5

    # Fallback env var
    monkeypatch.delenv("KITABIM_OCR_ZOOM_FACTOR", raising=False)
    monkeypatch.setenv("OCR_PAGE_ZOOM_FACTOR", "2.8")
    assert get_configured_zoom_factor() == 2.8

    # Clamping behavior
    monkeypatch.setenv("KITABIM_OCR_ZOOM_FACTOR", "1.0")
    assert get_configured_zoom_factor() == 1.5
    monkeypatch.setenv("KITABIM_OCR_ZOOM_FACTOR", "10.0")
    assert get_configured_zoom_factor() == 5.0

    # Invalid string falls back to default
    monkeypatch.setenv("KITABIM_OCR_ZOOM_FACTOR", "invalid")
    assert get_configured_zoom_factor() == DEFAULT_OCR_PAGE_ZOOM_FACTOR


def test_is_dot_enhancement_enabled(monkeypatch):
    monkeypatch.delenv("KITABIM_OCR_DOT_ENHANCEMENT", raising=False)
    monkeypatch.delenv("OCR_DOT_ENHANCEMENT", raising=False)
    assert DEFAULT_OCR_DOT_ENHANCEMENT is True
    assert is_dot_enhancement_enabled() is True

    for disabled_val in ("false", "0", "no", "off", "disable", "disabled"):
        monkeypatch.setenv("KITABIM_OCR_DOT_ENHANCEMENT", disabled_val)
        assert is_dot_enhancement_enabled() is False

    for enabled_val in ("true", "1", "yes", "on"):
        monkeypatch.setenv("KITABIM_OCR_DOT_ENHANCEMENT", enabled_val)
        assert is_dot_enhancement_enabled() is True

    # Fallback to OCR_DOT_ENHANCEMENT
    monkeypatch.delenv("KITABIM_OCR_DOT_ENHANCEMENT", raising=False)
    monkeypatch.setenv("OCR_DOT_ENHANCEMENT", "false")
    assert is_dot_enhancement_enabled() is False


def test_get_chandra_prompt_type(monkeypatch):
    monkeypatch.delenv("KITABIM_CHANDRA_PROMPT_TYPE", raising=False)
    monkeypatch.delenv("CHANDRA_PROMPT_TYPE", raising=False)
    assert get_chandra_prompt_type() == DEFAULT_CHANDRA_PROMPT_TYPE
    assert get_chandra_prompt_type() == "ocr_layout"

    monkeypatch.setenv("KITABIM_CHANDRA_PROMPT_TYPE", "ocr")
    assert get_chandra_prompt_type() == "ocr"

    # Unsupported value falls back to default
    monkeypatch.setenv("KITABIM_CHANDRA_PROMPT_TYPE", "unsupported_mode")
    assert get_chandra_prompt_type() == DEFAULT_CHANDRA_PROMPT_TYPE


def test_get_chandra_prompt_guidance(monkeypatch):
    monkeypatch.delenv("KITABIM_CHANDRA_PROMPT_GUIDANCE", raising=False)
    monkeypatch.delenv("CHANDRA_PROMPT_GUIDANCE", raising=False)
    assert get_chandra_prompt_guidance() == DEFAULT_CHANDRA_PROMPT_GUIDANCE

    custom = "Transcribe modern Uyghur text."
    monkeypatch.setenv("KITABIM_CHANDRA_PROMPT_GUIDANCE", custom)
    assert get_chandra_prompt_guidance() == custom

    # Disable keywords
    for disable_val in ("none", "false", "0", "disabled", "off"):
        monkeypatch.setenv("KITABIM_CHANDRA_PROMPT_GUIDANCE", disable_val)
        assert get_chandra_prompt_guidance() == ""


def test_get_chandra_repetition_penalty(monkeypatch):
    monkeypatch.delenv("KITABIM_CHANDRA_REPETITION_PENALTY", raising=False)
    monkeypatch.delenv("CHANDRA_REPETITION_PENALTY", raising=False)
    assert get_chandra_repetition_penalty() == DEFAULT_CHANDRA_REPETITION_PENALTY
    assert get_chandra_repetition_penalty() == 1.05

    monkeypatch.setenv("KITABIM_CHANDRA_REPETITION_PENALTY", "1.15")
    assert get_chandra_repetition_penalty() == 1.15

    # Out of bounds clamping
    monkeypatch.setenv("KITABIM_CHANDRA_REPETITION_PENALTY", "0.5")
    assert get_chandra_repetition_penalty() == 1.0
    monkeypatch.setenv("KITABIM_CHANDRA_REPETITION_PENALTY", "5.0")
    assert get_chandra_repetition_penalty() == 2.0


def test_get_chandra_min_image_dim(monkeypatch):
    monkeypatch.delenv("KITABIM_CHANDRA_MIN_IMAGE_DIM", raising=False)
    monkeypatch.delenv("CHANDRA_MIN_IMAGE_DIM", raising=False)
    assert get_chandra_min_image_dim() == DEFAULT_CHANDRA_MIN_IMAGE_DIM
    assert get_chandra_min_image_dim() == 1536

    monkeypatch.setenv("KITABIM_CHANDRA_MIN_IMAGE_DIM", "2048")
    assert get_chandra_min_image_dim() == 2048
