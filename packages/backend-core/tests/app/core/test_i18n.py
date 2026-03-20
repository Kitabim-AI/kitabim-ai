from unittest.mock import patch
import json
from app.core.i18n import I18n, t, get_current_lang, set_current_lang

def test_i18n_basic():
    # Mock translations dictionary directly to avoid filesystem dependency
    I18n._translations = {
        "en": {"hello": "Hello {name}", "nested": {"key": "Value"}},
        "ug": {"hello": "ياخشىمۇسىز {name}"}
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

def test_load_translations(tmp_path):
    # Mocking filesystem
    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "en.json").write_text(json.dumps({"test": "value"}))
    
    with patch.object(I18n, "_locales_dir", str(locales)):
        I18n.load_translations()
        assert "en" in I18n._translations
        assert I18n._translations["en"]["test"] == "value"
