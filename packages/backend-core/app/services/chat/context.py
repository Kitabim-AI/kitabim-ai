"""Chat request DTO and tool dependencies container for ADK chat architecture"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ChatRequestDTO:
    """Immutable data transfer object representing a chat request"""

    question: str
    user_id: str
    book_id: Optional[str] = None
    is_global: bool = False
    current_page: Optional[int] = None
    character_id: Optional[str] = None
    conversation_id: Optional[str] = None
    context_book_ids: Optional[List[str]] = None


@dataclass
class ToolDependencies:
    """Service container injected into ADK tools"""

    db_session: AsyncSession
    active_book_id: Optional[str] = None
    is_global: bool = False
    current_page: Optional[int] = None
    rag_chain: Optional[Any] = None
    persona_prompt: Optional[str] = None
