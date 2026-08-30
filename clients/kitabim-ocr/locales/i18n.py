from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

LOCALES_DIR = Path(__file__).resolve().parent

_translations: dict[str, dict[str, Any]] = {}


def load_translations() -> dict[str, dict[str, Any]]:
    global _translations
    if not _translations:
        for json_file in LOCALES_DIR.glob("*.json"):
            lang = json_file.stem
            try:
                _translations[lang] = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                continue
    return _translations


def get_translations(lang: str = "ug") -> dict[str, Any]:
    translations = load_translations()
    if lang in translations:
        return translations[lang]
    if "ug" in translations:
        return translations["ug"]
    if "en" in translations:
        return translations["en"]
    return {}


def get_translations_json(lang: str = "ug") -> str:
    return json.dumps(get_translations(lang), ensure_ascii=False)


def t(
    key: str,
    lang: str = "ug",
    default: Optional[str] = None,
    **kwargs: Any,
) -> str:
    translations = load_translations()
    target_dict = (
        translations.get(lang) or translations.get("ug") or translations.get("en") or {}
    )

    def _get_nested(d: dict[str, Any], k: str) -> Optional[str]:
        curr: Any = d
        for part in k.split("."):
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                return None
        return curr if isinstance(curr, str) else None

    text = _get_nested(target_dict, key)
    if text is None and lang != "en" and "en" in translations:
        text = _get_nested(translations["en"], key)

    if text is None:
        text = default if default is not None else key

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            return text
    return text
