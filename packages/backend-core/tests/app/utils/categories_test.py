import re
from pathlib import Path

from app.utils.categories import (
    CATEGORY_ALIASES,
    normalize_categories,
    normalize_category,
)

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "099_normalize_book_categories.sql"
)


def test_strips_zero_width_characters():
    assert normalize_category("ئ‍ىسلام") == "ئىسلام"
    assert normalize_category("ئ‍ەرەبچە") == "ئەرەبچە"
    assert normalize_category("﻿رومان​") == "رومان"


def test_trims_whitespace_and_quotes():
    assert normalize_category('  "رومان" ') == "رومان"


def test_maps_variants_to_canonical_names():
    assert normalize_category("مۇۋاپېقىيەتشۇناسلىق") == "مۇۋەپپەقىيەتشۇناسلىق"
    assert normalize_category("مۇۋاپپىقىيەتشۇناسلىق") == "مۇۋەپپەقىيەتشۇناسلىق"
    assert normalize_category("ماقالىلار") == "ماقالىلەر"
    assert normalize_category("نەسرلەر") == "نەسىرلەر"
    assert normalize_category("ئەدەبىي ئاخبارات") == "ئەدەبىي ئاخباراتلار"
    assert normalize_category("تەزكىرە") == "تەزكىرىلەر"


def test_canonical_names_are_unchanged():
    for canonical in set(CATEGORY_ALIASES.values()):
        assert normalize_category(canonical) == canonical


def test_normalize_categories_dedupes_keeps_order_and_drops_empties():
    assert normalize_categories(
        ["ماقالىلار", "رومان", "ماقالىلەر", "  ", '""', "ئ‍ىسلام", None]
    ) == ["ماقالىلەر", "رومان", "ئىسلام"]


def test_normalize_categories_handles_none():
    assert normalize_categories(None) == []


def test_migration_mapping_matches_python_aliases():
    """Migration 099 and the input-side helper must apply the same renames,
    or edits through the API would reintroduce variants the migration merged."""
    sql = MIGRATION.read_text(encoding="utf-8")
    pairs = dict(re.findall(r"\('([^']+)',\s*'([^']+)'\)", sql))
    assert pairs == CATEGORY_ALIASES


def test_persona_categories_are_canonical():
    """Persona filters match books.categories exactly, so every persona
    category must already be in normalized, canonical form."""
    from app.core.characters import CHARACTERS

    for character in CHARACTERS.values():
        for category in character.categories:
            assert normalize_category(category) == category, (character.id, category)
