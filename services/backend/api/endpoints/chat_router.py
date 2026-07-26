import logging
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession


from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.db.session import get_session
from app.models.schemas import ChatRequest, ChatResponse, ChatUsageStatus
from app.models.user import User
from app.services.chat.context import ChatRequestDTO
from app.services.chat.orchestrator import ChatOrchestrator
from app.services.rag_service import get_rag_service, RAGService
from app.services.chat_limit_service import chat_limit_service
from app.utils.errors import record_book_error
from app.utils.observability import log_json
from app.utils.citation_fixer import fix_malformed_citations
from auth.dependencies import require_reader
from app.core.i18n import t

router = APIRouter()
logger = logging.getLogger("app.chat")


@router.get("/usage", response_model=ChatUsageStatus)
async def get_chat_usage(
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Get current user's chat usage and limit status."""
    return await chat_limit_service.get_user_usage_status(current_user, session)


@router.post("/", response_model=ChatResponse)
async def chat_with_book_api(
    req: ChatRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
    rag_service: RAGService = Depends(get_rag_service),
):
    """Chat with book using RAG with SQLAlchemy and role-based daily limits"""
    log_json(
        logger,
        logging.INFO,
        "Chat endpoint entered",
        user_id=current_user.id,
        book_id=req.book_id,
    )
    # 1. Check if user is within their daily limit
    usage_status = await chat_limit_service.get_user_usage_status(current_user, session)
    if usage_status["has_reached_limit"]:
        log_json(
            logger,
            logging.WARNING,
            "Chat limit reached for user",
            user_id=current_user.id,
            role=current_user.role,
            usage=usage_status["usage"],
            limit=usage_status["limit"],
        )
        raise HTTPException(status_code=429, detail=t("errors.daily_limit_reached"))

    try:
        # 2. Process chat request
        answer = await rag_service.answer_question(
            req, session, user_id=current_user.id
        )

        # 2.5. Fix malformed citation references
        answer = fix_malformed_citations(answer)

        # 3. Increment usage on successful answer
        await chat_limit_service.increment_usage(current_user, session)
        usage_status = await chat_limit_service.get_user_usage_status(
            current_user, session
        )

        return {"answer": answer, "usage": usage_status}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        error_str = str(exc)
        log_json(
            logger,
            logging.ERROR,
            "Chat request failed",
            book_id=req.book_id,
            error=error_str,
        )

        # Check for 429 RESOURCE_EXHAUSTED from Google/Gemini
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            raise HTTPException(status_code=429, detail=t("errors.system_busy"))

        # Record error using SQLAlchemy
        await record_book_error(session, req.book_id, "chat", error_str)
        raise HTTPException(status_code=500, detail=t("errors.system_busy_generic"))


@router.post("/stream")
async def chat_with_book_stream(
    req: ChatRequest,
    request: Request,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
    rag_service: RAGService = Depends(get_rag_service),
):
    """Stream chat responses using Server-Sent Events (SSE)"""
    log_json(
        logger,
        logging.INFO,
        "Chat stream endpoint entered",
        user_id=current_user.id,
        book_id=req.book_id,
    )

    # Check if user is within their daily limit
    usage_status = await chat_limit_service.get_user_usage_status(current_user, session)
    if usage_status["has_reached_limit"]:
        log_json(
            logger,
            logging.WARNING,
            "Chat limit reached for user (stream)",
            user_id=current_user.id,
            role=current_user.role,
            usage=usage_status["usage"],
            limit=usage_status["limit"],
        )

        async def error_stream():
            yield f"data: {json.dumps({'error': t('errors.daily_limit_reached')})}\n\n"

        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def event_generator():
        try:
            config_repo = SystemConfigsRepository(session)
            config_value = await config_repo.get_value("use_adk_chat_v2")
            use_v2 = (config_value == "true") or bool(req.conversation_id)

            if use_v2:
                adk_session_service = getattr(
                    request.app.state, "adk_session_service", None
                )
                orchestrator = ChatOrchestrator(session_service=adk_session_service)

                is_global = req.is_global or req.book_id == "global"
                dto = ChatRequestDTO(
                    question=req.question,
                    user_id=current_user.id,
                    book_id=req.book_id,
                    is_global=is_global,
                    current_page=req.current_page,
                    character_id=req.character_id,
                    conversation_id=req.conversation_id,
                    context_book_ids=req.context_book_ids,
                )

                async for event in orchestrator.stream_response(dto, session):
                    if isinstance(event, dict):
                        if event.get("type") == "chunk":
                            yield f"data: {json.dumps({'chunk': event['text']})}\n\n"
                        elif event.get("type") == "done":
                            await chat_limit_service.increment_usage(
                                current_user, session
                            )
                            updated_usage = (
                                await chat_limit_service.get_user_usage_status(
                                    current_user, session
                                )
                            )
                            done_payload = {
                                "done": True,
                                "usage": updated_usage,
                                "conversationId": event.get("conversation_id"),
                                "contextBookIds": event.get("used_book_ids", []),
                                "evalId": event.get("eval_id"),
                            }
                            yield f"data: {json.dumps(done_payload)}\n\n"
                        else:
                            yield f"data: {json.dumps(event)}\n\n"
                return

            accumulated_response = ""
            stream_meta: dict = {}
            # Stream events from RAG service.
            async for event in rag_service.answer_question_stream(
                req, session, user_id=current_user.id, metadata_out=stream_meta
            ):
                if isinstance(event, str):
                    accumulated_response += event
                    yield f"data: {json.dumps({'chunk': event})}\n\n"
                elif isinstance(event, dict):
                    if event.get("type") == "chunk":
                        accumulated_response += event.get("text", "")
                        yield f"data: {json.dumps({'chunk': event['text']})}\n\n"
                    elif event.get("type") == "answer_start":
                        accumulated_response = ""
                        yield f"data: {json.dumps(event)}\n\n"
                    else:
                        yield f"data: {json.dumps(event)}\n\n"

            # After streaming completes, apply citation fixer and send fixed version if needed
            fixed_response = fix_malformed_citations(accumulated_response)
            if fixed_response != accumulated_response:
                log_json(
                    logger,
                    logging.INFO,
                    "Citations were fixed in stream",
                    user_id=current_user.id,
                )
                yield f"data: {json.dumps({'correction': fixed_response})}\n\n"

            # Increment usage on successful stream completion
            await chat_limit_service.increment_usage(current_user, session)
            updated_usage = await chat_limit_service.get_user_usage_status(
                current_user, session
            )

            yield f"data: {json.dumps({'done': True, 'usage': updated_usage, 'contextBookIds': stream_meta.get('used_book_ids', []), 'evalId': stream_meta.get('eval_id')})}\n\n"

        except ValueError as exc:
            # Book not found or validation error
            log_json(logger, logging.WARNING, "Stream validation error", error=str(exc))
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        except Exception as exc:
            error_str = str(exc)
            log_json(
                logger,
                logging.ERROR,
                "Stream failed",
                book_id=req.book_id,
                error=error_str,
            )

            # Check for rate limit errors from Gemini
            error_msg = t("errors.system_busy_generic")

            yield f"data: {json.dumps({'error': error_msg})}\n\n"
            try:
                await record_book_error(session, req.book_id, "chat_stream", error_str)
            except Exception as record_exc:
                log_json(
                    logger,
                    logging.WARNING,
                    "record_book_error failed",
                    error=str(record_exc),
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    eval_id: int
    feedback: str  # "positive" | "negative"


@router.post("/feedback")
async def submit_chat_feedback(
    req: FeedbackRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Record thumbs-up/down feedback for an assistant response."""
    if req.feedback not in ("positive", "negative"):
        raise HTTPException(
            status_code=400, detail="feedback must be 'positive' or 'negative'"
        )

    from app.db.repositories.rag_evaluations_repository import RAGEvaluationsRepository
    from app.db.models import RAGEvaluation

    # Verify the record exists and belongs to this user before mutating it.
    # eval_id is a sequential integer — without this check any authenticated
    # reader could trigger updates on other users' responses.
    record = await session.get(RAGEvaluation, req.eval_id)
    if record is None or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Evaluation record not found")

    repo = RAGEvaluationsRepository(session)
    evaluation = await repo.update_feedback(
        eval_id=req.eval_id,
        feedback=req.feedback,
    )

    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation record not found")

    log_json(
        logger,
        logging.INFO,
        "Chat feedback recorded",
        eval_id=req.eval_id,
        user_id=current_user.id,
        feedback=req.feedback,
    )

    return {"ok": True, "eval_id": req.eval_id, "feedback": req.feedback}


@router.get("/recent-questions")
async def get_recent_questions(
    limit: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """Return recent distinct first-turn questions for the home page rotator.

    No auth required — these are public showcase questions.
    """
    from app.db.repositories.rag_evaluations_repository import RAGEvaluationsRepository

    repo = RAGEvaluationsRepository(session)
    questions = await repo.get_recent_standalone_questions(limit=limit)
    return {"questions": questions}


# ---------------------------------------------------------------------------
# Conversation endpoints
# ---------------------------------------------------------------------------


class CreateConversationRequest(BaseModel):
    book_id: Optional[str] = None
    is_global: bool = False
    title: Optional[str] = None


@router.post("/conversations")
async def create_conversation_endpoint(
    req: CreateConversationRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Create a new conversation session"""

    repo = ConversationRepository(session)
    conv = await repo.create_conversation(
        user_id=current_user.id,
        book_id=req.book_id,
        is_global=req.is_global,
        title=req.title,
    )
    return {
        "id": conv.id,
        "userId": conv.user_id,
        "bookId": conv.book_id,
        "bookTitle": conv.book.title if conv.book else None,
        "isGlobal": conv.is_global,
        "title": conv.title,
        "createdAt": conv.created_at.isoformat(),
        "updatedAt": conv.updated_at.isoformat(),
    }


@router.get("/conversations")
async def list_conversations_endpoint(
    limit: int = 50,
    offset: int = 0,
    book_id: Optional[str] = None,
    is_global: Optional[bool] = None,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """List current user's conversations"""

    repo = ConversationRepository(session)
    conversations = await repo.list_user_conversations(
        current_user.id,
        limit=limit,
        offset=offset,
        book_id=book_id,
        is_global=is_global,
    )
    return {
        "conversations": [
            {
                "id": c.id,
                "userId": c.user_id,
                "bookId": c.book_id,
                "bookTitle": c.book.title if c.book else None,
                "isGlobal": c.is_global,
                "title": c.title,
                "createdAt": c.created_at.isoformat(),
                "updatedAt": c.updated_at.isoformat(),
            }
            for c in conversations
        ]
    }


@router.get("/conversations/{conversation_id}/messages")
async def list_conversation_messages_endpoint(
    conversation_id: str,
    limit: int = 100,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Get message history for a conversation"""

    repo = ConversationRepository(session)
    conv = await repo.get_conversation(conversation_id)
    if conv is None or conv.user_id != current_user.id:
        raise HTTPException(status_code=404, detail=t("errors.conversation_not_found"))

    messages = await repo.get_conversation_messages(conversation_id, limit=limit)
    return {
        "messages": [
            {
                "id": m.id,
                "conversationId": m.conversation_id,
                "role": m.role,
                "content": m.content,
                "agentSteps": m.agent_steps,
                "usedBookIds": m.used_book_ids,
                "currentPage": m.current_page,
                "evalId": m.eval_id,
                "createdAt": m.created_at.isoformat(),
            }
            for m in messages
        ]
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: str,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Delete a conversation by ID"""

    repo = ConversationRepository(session)
    deleted = await repo.delete_conversation(conversation_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail=t("errors.conversation_not_found"))
    return {"ok": True, "id": conversation_id}
