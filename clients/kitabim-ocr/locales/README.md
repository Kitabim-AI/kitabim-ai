# Kitabim OCR Locales

## Overview
Internationalization and localization dictionary loader for the Kitabim OCR client application. Provides translation lookups, nested key resolution, fallback chain evaluation (Uyghur -> English), and string formatting across the UI.

## Interface
- `[i18n.py:load_translations]`: Loads translation dictionaries from `*.json` files into an in-memory cache.
- `[i18n.py:get_translations]`: Returns the dictionary for a requested language, defaulting to `'ug'`.
- `[i18n.py:get_translations_json]`: Returns a JSON-serialized string of the translation map for web client delivery.
- `[i18n.py:t]`: Resolves dot-delimited translation keys with fallback and kwargs interpolation.
- `[__init__.py:t]`: Re-exports translation helper functions (`t`, `get_translations`, `get_translations_json`, `load_translations`).

## Invariants
- `[i18n.py:t]`: Language resolution falls back strictly in order: requested language -> `'ug'` -> `'en'` -> raw key.
- `[i18n.py:load_translations]`: Dictionaries are loaded once on demand and held in process memory.

## Side Effects
- `[i18n.py:load_translations]`: Reads locale files (`en.json`, `ug.json`) from disk upon initialization.

## Verification
- Run: `pytest clients/kitabim-ocr/tests`
