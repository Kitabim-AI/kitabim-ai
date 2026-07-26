"""Tests for ConversationRepository"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.db.models import Conversation, ConversationMessage
from app.db.repositories.conversation_repository import (
    ConversationRepository,
    get_conversation_repository,
)


@pytest.mark.asyncio
async def test_create_conversation_uses_default_title():
    session = AsyncMock()
    session.add = MagicMock()
    repo = ConversationRepository(session)

    conversation = await repo.create_conversation(user_id="user-1", book_id="book-1")

    assert conversation.user_id == "user-1"
    assert conversation.book_id == "book-1"
    assert conversation.is_global is False
    assert conversation.title  # falls back to the i18n default, never empty
    assert session.add.called
    assert session.flush.called
    assert session.refresh.called


@pytest.mark.asyncio
async def test_create_conversation_uses_given_title():
    session = AsyncMock()
    session.add = MagicMock()
    repo = ConversationRepository(session)

    conversation = await repo.create_conversation(
        user_id="user-1", is_global=True, title="My chat"
    )

    assert conversation.is_global is True
    assert conversation.title == "My chat"


@pytest.mark.asyncio
async def test_get_conversation_found():
    session = AsyncMock()
    repo = ConversationRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Conversation(id="conv-1", user_id="u1")
    session.execute.return_value = mock_res

    conversation = await repo.get_conversation("conv-1")
    assert conversation.id == "conv-1"


@pytest.mark.asyncio
async def test_get_conversation_not_found():
    session = AsyncMock()
    repo = ConversationRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res

    conversation = await repo.get_conversation("missing")
    assert conversation is None


@pytest.mark.asyncio
async def test_get_conversation_query_excludes_soft_deleted():
    session = AsyncMock()
    repo = ConversationRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res

    await repo.get_conversation("conv-1")

    stmt = session.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "deleted_at IS NULL" in compiled


@pytest.mark.asyncio
async def test_list_user_conversations():
    session = AsyncMock()
    repo = ConversationRepository(session)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [
        Conversation(id="c1", user_id="u1"),
        Conversation(id="c2", user_id="u1"),
    ]
    session.execute.return_value = mock_res

    conversations = await repo.list_user_conversations("u1")
    assert len(conversations) == 2


@pytest.mark.asyncio
async def test_list_user_conversations_query_excludes_soft_deleted():
    session = AsyncMock()
    repo = ConversationRepository(session)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_res

    await repo.list_user_conversations("u1")

    stmt = session.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "deleted_at IS NULL" in compiled


@pytest.mark.asyncio
async def test_list_user_conversations_filters_by_book_id():
    session = AsyncMock()
    repo = ConversationRepository(session)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [
        Conversation(id="c1", user_id="u1", book_id="book-123"),
    ]
    session.execute.return_value = mock_res

    conversations = await repo.list_user_conversations("u1", book_id="book-123")
    assert len(conversations) == 1

    stmt = session.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "book_id = 'book-123'" in compiled


@pytest.mark.asyncio
async def test_list_user_conversations_filters_by_is_global():
    session = AsyncMock()
    repo = ConversationRepository(session)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [
        Conversation(id="c1", user_id="u1", is_global=True),
    ]
    session.execute.return_value = mock_res

    conversations = await repo.list_user_conversations("u1", is_global=True)
    assert len(conversations) == 1

    stmt = session.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "is_global is true" in compiled.lower()


@pytest.mark.asyncio
async def test_add_message_touches_conversation_and_flushes():
    session = AsyncMock()
    session.add = MagicMock()
    repo = ConversationRepository(session)

    msg = await repo.add_message(conversation_id="conv-1", role="user", content="Salam")

    assert msg.conversation_id == "conv-1"
    assert msg.role == "user"
    assert msg.content == "Salam"
    assert session.add.called
    # One execute call to bump conversations.updated_at
    session.execute.assert_awaited_once()
    assert session.flush.called
    assert session.refresh.called


@pytest.mark.asyncio
async def test_get_recent_messages_returns_oldest_to_newest():
    session = AsyncMock()
    repo = ConversationRepository(session)

    newest_first = [
        ConversationMessage(id="m2", conversation_id="c1", role="model", content="b"),
        ConversationMessage(id="m1", conversation_id="c1", role="user", content="a"),
    ]
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = newest_first
    session.execute.return_value = mock_res

    messages = await repo.get_recent_messages("c1", limit=10)
    assert [m.id for m in messages] == ["m1", "m2"]


@pytest.mark.asyncio
async def test_save_turn_saves_user_then_model_message():
    session = AsyncMock()
    session.add = MagicMock()
    repo = ConversationRepository(session)

    # save_turn looks up the conversation first to decide whether to
    # auto-generate a title; give it an already-titled conversation so
    # that branch is skipped and only the two add_message touch-updates follow.
    get_conv_res = MagicMock()
    get_conv_res.scalar_one_or_none.return_value = Conversation(
        id="conv-1", user_id="u1", title="Existing chat"
    )
    touch_res = MagicMock()
    session.execute.side_effect = [get_conv_res, touch_res, touch_res]

    user_msg, model_msg = await repo.save_turn(
        conversation_id="conv-1",
        question="سوئال",
        answer="جاۋاب",
        used_book_ids={"books": ["b1"]},
        eval_id=7,
    )

    assert user_msg.role == "user"
    assert user_msg.content == "سوئال"
    assert model_msg.role == "model"
    assert model_msg.content == "جاۋاب"
    assert model_msg.eval_id == 7
    assert model_msg.used_book_ids == {"books": ["b1"]}


@pytest.mark.asyncio
async def test_save_turn_generates_title_from_first_question():
    session = AsyncMock()
    session.add = MagicMock()
    repo = ConversationRepository(session)

    # A freshly-created conversation still has the default placeholder title.
    get_conv_res = MagicMock()
    get_conv_res.scalar_one_or_none.return_value = Conversation(
        id="conv-1", user_id="u1", title="يېڭى سۆھبەت"
    )
    update_title_exec_res = MagicMock()
    update_title_get_res = MagicMock()
    update_title_get_res.scalar_one_or_none.return_value = Conversation(
        id="conv-1", user_id="u1", title="سوئال"
    )
    touch_res = MagicMock()
    session.execute.side_effect = [
        get_conv_res,  # save_turn's own get_conversation check
        update_title_exec_res,  # update_title's UPDATE statement
        update_title_get_res,  # update_title's own get_conversation
        touch_res,  # add_message (user) touch-update
        touch_res,  # add_message (model) touch-update
    ]

    await repo.save_turn(conversation_id="conv-1", question="سوئال", answer="جاۋاب")

    # 3rd call is update_title's UPDATE statement — assert it sets a title.
    update_stmt = session.execute.call_args_list[1].args[0]
    compiled = str(update_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "title" in compiled.lower()


@pytest.mark.asyncio
async def test_update_title():
    session = AsyncMock()
    repo = ConversationRepository(session)

    get_res = MagicMock()
    get_res.scalar_one_or_none.return_value = Conversation(
        id="conv-1", user_id="u1", title="New title"
    )
    session.execute.side_effect = [MagicMock(), get_res]

    conversation = await repo.update_title("conv-1", "New title")
    assert conversation.title == "New title"


@pytest.mark.asyncio
async def test_delete_conversation_soft_deletes_and_returns_true():
    session = AsyncMock()
    repo = ConversationRepository(session)

    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res

    deleted = await repo.delete_conversation("conv-1", "user-1")
    assert deleted is True

    # It must be a soft delete (UPDATE ... SET deleted_at), never a DELETE.
    stmt = session.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert compiled.strip().upper().startswith("UPDATE")
    assert "deleted_at" in compiled


@pytest.mark.asyncio
async def test_delete_conversation_not_owned_returns_false():
    session = AsyncMock()
    repo = ConversationRepository(session)

    mock_res = MagicMock()
    mock_res.rowcount = 0
    session.execute.return_value = mock_res

    deleted = await repo.delete_conversation("conv-1", "other-user")
    assert deleted is False


@pytest.mark.asyncio
async def test_delete_conversation_already_deleted_is_idempotent():
    session = AsyncMock()
    repo = ConversationRepository(session)

    # Re-deleting an already soft-deleted conversation matches zero rows
    # (the WHERE clause excludes rows that already have deleted_at set).
    mock_res = MagicMock()
    mock_res.rowcount = 0
    session.execute.return_value = mock_res

    deleted = await repo.delete_conversation("conv-1", "user-1")
    assert deleted is False


def test_get_conversation_repository_factory():
    session = AsyncMock()
    repo = get_conversation_repository(session)
    assert isinstance(repo, ConversationRepository)
