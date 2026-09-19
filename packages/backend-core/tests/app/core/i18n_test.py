from unittest.mock import patch
import json
from app.core.i18n import I18n, t, get_current_lang, set_current_lang


def test_i18n_basic():
    # Mock translations dictionary directly to avoid filesystem dependency.
    # Both _translations and the current-language ContextVar are process-wide
    # state shared with every other test module (e.g. test_adk_orchestrator.py
    # relies on the real ug/en translations) -- restore both on exit so this
    # test doesn't leak a stubbed-out dictionary or "fr" as the active
    # language into whatever test runs next.
    original_translations = I18n._translations
    original_lang = get_current_lang()
    try:
        I18n._translations = {
            "en": {"hello": "Hello {name}", "nested": {"key": "Value"}},
            "ug": {"hello": "ياخشىمۇسىز {name}"},
        }

        # Simple t call
        set_current_lang("en")
        assert t("hello", name="World") == "Hello World"

        # Nested key
        assert I18n.t("nested.key") == "Value"

        # Language override
        assert I18n.t("hello", lang="ug", name="ئۆمەر") == "ياخشىمۇسىز ئۆمەر"

        # Fallback to English
        set_current_lang("ug")
        assert I18n.t("nested.key") == "Value"

        # Missing key
        assert t("missing") == "missing"

        # Current lang
        set_current_lang("fr")
        assert get_current_lang() == "fr"
    finally:
        I18n._translations = original_translations
        set_current_lang(original_lang)


def test_load_translations(tmp_path):
    # Mocking filesystem
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "en.json").write_text(json.dumps({"test": "value"}))

    with patch.object(I18n, "_locales_dir", str(locales)):
        I18n.load_translations()
        assert "en" in I18n._translations
        assert I18n._translations["en"]["test"] == "value"
