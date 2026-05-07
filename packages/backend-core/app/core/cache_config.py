from __future__ import annotations
from app.core.config import settings

# Cache TTL constants (seconds) - linked to settings
TTL_BOOKS = settings.cache_ttl_books
TTL_SYSTEM_CONFIG = settings.cache_ttl_system_config
TTL_CATEGORIES = settings.cache_ttl_categories
TTL_RAG_QUERY = settings.cache_ttl_rag_query
TTL_USER_PROFILE = settings.cache_ttl_user_profile
TTL_STATS = settings.cache_ttl_stats
TTL_SUMMARY_SEARCH = settings.cache_ttl_summary_search

# Cache key patterns
KEY_BOOK = "book:{book_id}"
KEY_BOOKS_LIST = "books:list:{hash}"
KEY_CATEGORY = "category:{type}:{params}"
KEY_USER = "user:{user_id}"
KEY_RAG_EMBEDDING = "rag:embedding:{hash}"
KEY_RAG_SEARCH_SINGLE = "rag:search:{book_id}:{hash}"
KEY_RAG_SEARCH_MULTI = "rag:search:multi:{book_ids_hash}:{hash}"
KEY_RAG_SUMMARY_SEARCH = "rag:summary_search:{hash}"
KEY_PROVERB = "proverb:{hash}"
KEY_STATS = "stats:system"

KEY_CONFIG = "config:{key}"
KEY_CHAT_USAGE = "chat:usage:{user_id}:{date}"
KEY_RAG_REWRITE = "rag:rewrite:{hash}"

