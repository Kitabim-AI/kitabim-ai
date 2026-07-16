"""Centralized Uyghur & English keyword lists for RAG intent detection, routing, and query rewriting."""

from __future__ import annotations

# UYGHUR_PRONOUN_TOKENS: pronoun tokens for checking if a query needs rewrite
UYGHUR_PRONOUN_TOKENS = {
    # Singular
    "ئۇ",
    "بۇ",
    "شۇ",
    "ئۇنىڭ",
    "بۇنىڭ",
    "شۇنىڭ",
    "ئۇنى",
    "بۇنى",
    "شۇنى",
    "ئۇنىڭغا",
    "بۇنىڭغا",
    "شۇنىڭغا",
    "ئۇنىڭدا",
    "بۇنىڭدا",
    "شۇنىڭدا",
    "ئۇنىڭدىن",
    "بۇنىڭدىن",
    "شۇنىڭدىن",
    # Plural
    "ئۇلار",
    "بۇلار",
    "شۇلار",
    "ئۇلارنىڭ",
    "بۇلارنىڭ",
    "شۇلارنىڭ",
    "ئۇلارنى",
    "بۇلارنى",
    "شۇلارنى",
    "ئۇلارغا",
    "بۇلارغا",
    "شۇلارغا",
    "ئۇلاردا",
    "بۇلاردا",
    "شۇلاردا",
    "ئۇلاردىن",
    "بۇلاردىن",
    "شۇلاردىن",
    # Topic-shift clitics ("what about...")
    "ئۇچۇ",
    "بۇچۇ",
    "شۇچۇ",
    "ئۇلارچۇ",
    "بۇلارچۇ",
    "شۇلارچۇ",
}

# VOLUME_SHIFT_KEYWORDS: for volume shift detection (originally _VOLUME_SHIFT_KEYWORDS)
VOLUME_SHIFT_KEYWORDS = {
    "توم",
    "كەيىنكى توم",
    "ئالدىنقى توم",
    "كېيىنكى قىسىم",
    "ئالدىنقى قىسىم",
    "next volume",
    "prev volume",
    "previous volume",
}

# CURRENT_VOLUME_KEYWORDS: for is_current_volume_query
CURRENT_VOLUME_KEYWORDS = [
    "ئۇشبۇ تومدا",
    "مۇشۇ تومدا",
    "مۇشۇ قىسىمدا",
    "ئۇشبۇ قىسىمدا",
    "مەزكور تومدا",
    "مەزكور قىسىمدا",
    "بۇ تومدا",
    "بۇ قىسىمدا",
]

# CURRENT_PAGE_KEYWORDS: for is_current_page_query
CURRENT_PAGE_KEYWORDS = [
    "ئۇشبۇ بەتتە",
    "مەزكور بەتتە",
    "بۇ بەتتە",
    "مۇشۇ بەتتە",
]

# CURRENT_BOOK_KEYWORDS: deictic references to "this/the current book" (no title named)
CURRENT_BOOK_KEYWORDS = [
    "بۇ كىتاب",
    "مۇشۇ كىتاب",
    "ئۇشبۇ كىتاب",
    "مەزكور كىتاب",
    "this book",
]

# CATALOG_QUERY_KEYWORDS: for is_author_or_catalog_query
CATALOG_QUERY_KEYWORDS = [
    # Author-related — "who wrote X" / "author of X"
    "مۇئەللىپ",
    "مۇئەللىپى",
    "يازغۇچى",
    "يازغۇچىسى",
    "ئاپتور",
    "ئاپتورى",
    "كىم يازغان",
    "يازغان كىشى",
    "يازغان كىم",
    "كىم تەرىپىدىن",
    "يازغانلىقى",
    "كىمنىڭ",
    "كىمنىكى",
    # Author-related — "X's books / works"
    "ئەسەر يازغان",
    "ئەسەرلىرى",
    "كىتابلىرى",
    # Catalog / book-list related
    "كىتابلىرىڭىز",
    "كىتاب بارمۇ",
    "كىتابخانىڭىز",
    "كىتاب تىزىملىكى",
    "قانچە كىتاب",
    "نەچچە كىتاب",
    "قايسى كىتابلار",
    "قايسى ئەسەر",
]

# CONTENT_SIGNAL_KEYWORDS: content queries that override catalog keywords
CONTENT_SIGNAL_KEYWORDS = [
    "پېرسوناژ",
    "ئوبراز",
    "قەھرىمان",  # character references
    "قايسى ئەسەردىكى",
    "قايسى كىتابتا",  # "in which work/book" patterns
    "قايسى ئەسەردە",
    "قايسى كىتابدا",
]

# CATALOG_QUERY_PATTERNS: for planning / signal extraction (originally _CATALOG_PATTERNS)
CATALOG_QUERY_PATTERNS = {
    "كىم يازغان",
    "ئاپتورى كىم",
    "ئاپتور كىم",
    "نىمە يازغان",
    "قانداق كىتاب",
}

# PAGE_QUERY_PATTERNS: for planning (originally _PAGE_PATTERNS)
PAGE_QUERY_PATTERNS = {
    "بۇ بەتتە",
    "بەتتە نېمە",
    "بۇ بەت",
    "read this page",
    "current page",
}

# CATALOG_AUTHOR_QUERIES: for catalog subtype detection
CATALOG_AUTHOR_QUERIES = [
    "كىم يازغان",
    "ئاپتورى كىم",
    "ئاپتور كىم",
]

# CATALOG_BOOKS_QUERIES: for catalog subtype detection
CATALOG_BOOKS_QUERIES = [
    "نىمە يازغان",
    "قانداق كىتاب",
]
