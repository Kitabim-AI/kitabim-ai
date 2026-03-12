import pytest
from app.core.i18n import I18n, set_current_lang, get_current_lang, t

def test_i18n_basic():
    # Setup mock translations
    I18n._translations = {
        "en": {
            "hello": "Hello {name}",
            "nested": {"key": "Nested English"}
        },
        "ug": {
            "hello": "ياخشىمۇسىز {name}",
            "only_ug": "Uyghur only"
        }
    }
    
    # Test setting/getting context var
    set_current_lang("ug")
    assert get_current_lang() == "ug"
    
    # Test basic translation
    assert t("hello", name="Omar") == "ياخشىمۇسىز Omar"
    
    # Test nested key fallback to English (because nested isn't in ug)
    assert t("nested.key") == "Nested English"
    
    # Test kwargs error handling
    assert t("hello") == "ياخشىمۇسىز {name}"
    
    # Test missing key fallback
    assert t("missing.key") == "missing.key"
    
    # Switch to English
    set_current_lang("en")
    assert t("hello", name="Omar") == "Hello Omar"
