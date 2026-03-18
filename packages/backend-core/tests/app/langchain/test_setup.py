import pytest
from unittest.mock import patch, MagicMock
from app.langchain.setup import configure_langchain, _set_langsmith_env

def test_set_langsmith_env():
    # Patch settings at the module level where it is used
    with patch("app.langchain.setup.settings") as mock_settings:
        mock_settings.langchain_tracing_enabled = True
        mock_settings.langchain_project = "test-proj"
        with patch.dict("os.environ", {}):
            _set_langsmith_env()
            import os
            assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
            assert os.environ.get("LANGCHAIN_PROJECT") == "test-proj"

def test_configure_langchain():
    with patch("logging.getLogger"):
        with patch("app.langchain.setup.settings") as mock_settings:
            mock_settings.langchain_tracing_enabled = True
            mock_settings.langchain_cache_enabled = True
            mock_settings.langchain_project = "test-proj"
            with patch("app.langchain.setup.set_llm_cache") as mock_set_cache:
                with patch("app.langchain.setup._set_langsmith_env"):
                    configure_langchain()
                    assert mock_set_cache.called

def test_configure_langchain_cache_fail():
    with patch("logging.getLogger"):
        with patch("app.langchain.setup.settings") as mock_settings:
            mock_settings.langchain_cache_enabled = True
            with patch("app.langchain.setup.set_llm_cache", side_effect=Exception("fail")):
                configure_langchain()
                # Should catch and log warning
