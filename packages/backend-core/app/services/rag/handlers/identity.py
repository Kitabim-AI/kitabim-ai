"""IdentityHandler — answers 'who are you' questions with character persona info."""
from __future__ import annotations


from app.core.characters import CHARACTERS, DEFAULT_CHARACTER_ID
from app.core.i18n import t
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import normalize_uyghur, build_empty_response_message

_IDENTITY_KEYWORDS = [
    "سەن كىمسەن", "سىز كىمسىز",
    "ئۆزەڭنى تونۇشتۇر", "ئۆزۈڭنى تونۇشتۇر", "ئۆزىڭىزنى تونۇشتۇرۇڭ",
    "نامىڭ نېمە", "نامىڭىز نېمە",
    "ئىسمىڭ نېمە", "ئىسمىڭىز نېمە",
    "سەن كىم", "سىز كىم",
    "كىم سەن", "كىم سىز",
]
_IDENTITY_KEYWORDS_NORM = [normalize_uyghur(k) for k in _IDENTITY_KEYWORDS]


class IdentityHandler(QueryHandler):
    intent_name = "identity"
    priority = 10

    def can_handle(self, ctx: QueryContext) -> bool:
        q = normalize_uyghur(ctx.question.strip())
        return any(k in q for k in _IDENTITY_KEYWORDS_NORM)

    async def handle(self, ctx: QueryContext) -> str:
        char = CHARACTERS.get(ctx.character_id) or CHARACTERS.get(DEFAULT_CHARACTER_ID)
        if char:
            return f"{t('rag.identity_intro', name=char.name_uy)} {char.persona_uy}"
        return build_empty_response_message()
