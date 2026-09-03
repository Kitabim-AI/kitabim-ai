import pytest

from engine.config import (
    DEFAULT_OCR_ENGINE,
    get_configured_engine,
    get_savitr_model_path,
    is_apple_silicon,
    is_savitr_available,
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
