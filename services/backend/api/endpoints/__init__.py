"""API Endpoints"""

from . import (
    ai_router,
    auth_router,
    books_router,
    chat_router,
    users_router,
    system_configs_router,
    stats_router,
    contact_router,
    spell_check_router,
    auto_correct_rules_router,
    dictionary_router,
    share_router,
    cache_router,
)

__all__ = [
    "ai_router",
    "auth_router",
    "books_router",
    "chat_router",
    "users_router",
    "system_configs_router",
    "stats_router",
    "contact_router",
    "spell_check_router",
    "auto_correct_rules_router",
    "dictionary_router",
    "share_router",
    "cache_router",
]
