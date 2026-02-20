import json
import os
from functools import lru_cache
from typing import Dict, Any, Optional
from fastapi import Request
from contextvars import ContextVar

# Context variable to store current language for the request
_current_lang: ContextVar[str] = ContextVar("current_lang", default="ug")

class I18n:
    _translations: Dict[str, Dict[str, str]] = {}
    _locales_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "locales")

    @classmethod
    def load_translations(cls):
        for filename in os.listdir(cls._locales_dir):
            if filename.endswith(".json"):
                lang = filename[:-5]
                with open(os.path.join(cls._locales_dir, filename), "r", encoding="utf-8") as f:
                    cls._translations[lang] = json.load(f)

    @classmethod
    def t(cls, key: str, lang: Optional[str] = None, **kwargs) -> str:
        if not lang:
            lang = _current_lang.get()
        
        # Fallback to English if language not found
        if lang not in cls._translations:
            lang = "en"
        
        # If English also not loaded, fallback to raw key
        if lang not in cls._translations:
            return key
            
        text = cls._translations[lang].get(key, cls._translations.get("en", {}).get(key, key))
        
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                return text
        return text

def get_current_lang() -> str:
    return _current_lang.get()

def set_current_lang(lang: str):
    _current_lang.set(lang)

# Initialize translations
try:
    I18n.load_translations()
except Exception:
    # Handle initial load if directory doesn't exist yet or is empty
    pass

def t(key: str, **kwargs) -> str:
    return I18n.t(key, **kwargs)
