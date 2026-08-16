import json
import os
from typing import Dict, Optional
from contextvars import ContextVar

# Context variable to store current language for the request
_current_lang: ContextVar[str] = ContextVar("current_lang", default="ug")


class I18n:
    _translations: Dict[str, Dict[str, str]] = {}
    _locales_dir: str = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "locales"
    )

    @classmethod
    def load_translations(cls):
        search_dirs = [
            cls._locales_dir,
            os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                ),
                "services",
                "backend",
                "locales",
            ),
            os.path.abspath("services/backend/locales"),
        ]
        target_dir = None
        for d in search_dirs:
            if d and os.path.exists(d) and os.path.isdir(d) and os.listdir(d):
                target_dir = d
                break

        if not target_dir:
            return

        for filename in os.listdir(target_dir):
            if filename.endswith(".json"):
                lang = filename[:-5]
                with open(
                    os.path.join(target_dir, filename), "r", encoding="utf-8"
                ) as f:
                    cls._translations[lang] = json.load(f)

    @classmethod
    def t(
        cls,
        key: str,
        lang: Optional[str] = None,
        default: Optional[str] = None,
        **kwargs,
    ) -> str:
        if not cls._translations:
            cls.load_translations()

        if not lang:
            lang = _current_lang.get()

        # Fallback to English if language not found
        target_lang = lang if lang in cls._translations else "en"

        # If language not loaded, fallback to default or raw key
        if target_lang not in cls._translations:
            return default if default is not None else key

        def _get_nested(d: dict, k: str) -> Optional[str]:
            parts = k.split(".")
            curr = d
            for part in parts:
                if isinstance(curr, dict) and part in curr:
                    curr = curr[part]
                else:
                    return None
            return curr if isinstance(curr, str) else None

        text = _get_nested(cls._translations[target_lang], key)
        if text is None and target_lang != "en" and "en" in cls._translations:
            text = _get_nested(cls._translations["en"], key)

        if text is None:
            text = default if default is not None else key

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


def t(key: str, default: Optional[str] = None, **kwargs) -> str:
    return I18n.t(key, default=default, **kwargs)
