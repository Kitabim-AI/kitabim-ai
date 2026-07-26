"""Conversation repository for managing user multi-turn chat sessions and messages"""

from __future__ import annotations

import logging
from typing import List, Optional
from datetime import datetime, UTC

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.i18n import t
from app.db.models import Conversation, ConversationMessage
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger("app.db.repositories.conversation_repository")


class ConversationRepository(BaseRepository[Conversation]):
    """Repository for user conversations and messages"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Conversation)

    async def create_conversation(
        self,
        user_id: str,
        book_id: Optional[str] = None,
        is_global: bool = False,
        title: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation session"""
        if not title and book_id:
            from app.db.models import Book

            book_res = await self.session.execute(
                select(Book.title).where(Book.id == book_id)
            )
            book_title = book_res.scalar_one_or_none()
            if book_title:
                title = f"«{book_title}» ھەققىدە"

        conversation = Conversation(
            user_id=user_id,
            book_id=book_id,
            is_global=is_global,
            title=title or t("messages.new_conversation_title"),
        )
        self.session.add(conversation)
        await self.session.flush()
        await self.session.refresh(conversation)
        await self.session.commit()
        return conversation

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Fetch conversation by ID (excludes soft-deleted conversations)"""
        stmt = select(Conversation).where(
            Conversation.id == conversation_id, Conversation.deleted_at.is_(None)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_user_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        book_id: Optional[str] = None,
        is_global: Optional[bool] = None,
    ) -> List[Conversation]:
        """List active, non-deleted conversations for a user ordered by updated_at desc"""
        stmt = select(Conversation).where(
            Conversation.user_id == user_id, Conversation.deleted_at.is_(None)
        )
        if is_global is not None:
            stmt = stmt.where(Conversation.is_global.is_(is_global))
        if book_id is not None:
            stmt = stmt.where(Conversation.book_id == book_id)

        stmt = stmt.order_by(Conversation.updated_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        agent_steps: Optional[dict] = None,
        used_book_ids: Optional[dict] = None,
        current_page: Optional[int] = None,
        eval_id: Optional[int] = None,
    ) -> ConversationMessage:
        """Add a single message turn to conversation"""
        msg = ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            agent_steps=agent_steps,
            used_book_ids=used_book_ids,
            current_page=current_page,
            eval_id=eval_id,
        )
        self.session.add(msg)

        # Touch updated_at on conversation
        stmt = (
            sql_update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.flush()
        await self.session.refresh(msg)
        await self.session.commit()
        return msg

    async def get_conversation_messages(
        self, conversation_id: str, limit: int = 100
    ) -> List[ConversationMessage]:
        """Get all messages for a conversation ordered by created_at asc"""
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_messages(
        self, conversation_id: str, limit: int = 10
    ) -> List[ConversationMessage]:
        """Get recent message turns for fast pre-processing context"""
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def save_turn(
        self,
        conversation_id: str,
        question: str,
        answer: str,
        used_book_ids: Optional[dict] = None,
        eval_id: Optional[int] = None,
        current_page: Optional[int] = None,
        agent_steps: Optional[dict] = None,
    ) -> tuple[ConversationMessage, ConversationMessage]:
        """Save a complete user-question + model-answer turn"""
        conv = await self.get_conversation(conversation_id)
        if conv and (
            not conv.title
            or conv.title in ["يېڭى سۆھبەت", "New Conversation", "سۆھبەت"]
        ):
            cleaned_q = " ".join(question.strip().split())
            if cleaned_q:
                new_title = cleaned_q[:37] + "..." if len(cleaned_q) > 40 else cleaned_q
                await self.update_title(conversation_id, new_title)

        user_msg = await self.add_message(
            conversation_id=conversation_id,
            role="user",
            content=question,
            current_page=current_page,
        )
        model_msg = await self.add_message(
            conversation_id=conversation_id,
            role="model",
            content=answer,
            used_book_ids=used_book_ids,
            eval_id=eval_id,
            agent_steps=agent_steps,
        )
        return user_msg, model_msg

    async def update_title(
        self, conversation_id: str, title: str
    ) -> Optional[Conversation]:
        """Update conversation title"""
        stmt = (
            sql_update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(title=title, updated_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return await self.get_conversation(conversation_id)

    async def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Soft-delete a conversation if owned by user and not already deleted"""
        stmt = (
            sql_update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
            .values(deleted_at=datetime.now(UTC))
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0


def get_conversation_repository(session: AsyncSession) -> ConversationRepository:
    """Factory helper for ConversationRepository"""
    return ConversationRepository(session)
