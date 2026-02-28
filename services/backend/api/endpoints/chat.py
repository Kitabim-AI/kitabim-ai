import logging
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession


from app.db.session import get_session
from app.models.schemas import ChatRequest, ChatResponse, ChatUsageStatus
from app.models.user import User
from app.services.rag_service import rag_service
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
):
    """Chat with book using RAG with SQLAlchemy and role-based daily limits"""
    log_json(logger, logging.INFO, "Chat endpoint entered", user_id=current_user.id, book_id=req.book_id)
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
            limit=usage_status["limit"]
        )
        raise HTTPException(
            status_code=429,
            detail=t("errors.daily_limit_reached")
        )

    try:
        # 2. Process chat request
        answer = await rag_service.answer_question(req, session, user_id=current_user.id)

        # 2.5. Fix malformed citation references
        answer = fix_malformed_citations(answer)

        # 3. Increment usage on successful answer
        await chat_limit_service.increment_usage(current_user, session)

        return {"answer": answer}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        error_str = str(exc)
        log_json(logger, logging.ERROR, "Chat request failed", book_id=req.book_id, error=error_str)

        # Check for 429 RESOURCE_EXHAUSTED from Google/Gemini
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            raise HTTPException(
                status_code=429,
                detail=t("errors.system_busy")
            )

        # Record error using SQLAlchemy
        await record_book_error(session, req.book_id, "chat", error_str)
        raise HTTPException(
            status_code=500,
            detail=t("errors.system_busy_generic")
        )


@router.post("/stream")
async def chat_with_book_stream(
    req: ChatRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Stream chat responses using Server-Sent Events (SSE)"""
    log_json(logger, logging.INFO, "Chat stream endpoint entered", user_id=current_user.id, book_id=req.book_id)

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
            limit=usage_status["limit"]
        )

        async def error_stream():
            yield f'data: {json.dumps({"error": t("errors.daily_limit_reached")})}\n\n'

        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def event_generator():
        stream_completed = False
        accumulated_response = ""
        try:
            # Stream chunks from RAG service
            async for chunk in rag_service.answer_question_stream(req, session, user_id=current_user.id):
                accumulated_response += chunk
                yield f'data: {json.dumps({"chunk": chunk})}\n\n'

            # After streaming completes, apply citation fixer and send fixed version if needed
            fixed_response = fix_malformed_citations(accumulated_response)
            if fixed_response != accumulated_response:
                # Send the corrected version
                log_json(logger, logging.INFO, "Citations were fixed in stream", user_id=current_user.id)
                yield f'data: {json.dumps({"correction": fixed_response})}\n\n'

            stream_completed = True
            yield f'data: {json.dumps({"done": True})}\n\n'

        except ValueError as exc:
            # Book not found or validation error
            log_json(logger, logging.WARNING, "Stream validation error", error=str(exc))
            yield f'data: {json.dumps({"error": str(exc)})}\n\n'
        except Exception as exc:
            error_str = str(exc)
            log_json(logger, logging.ERROR, "Stream failed", book_id=req.book_id, error=error_str)

            # Check for rate limit errors from Gemini
            error_msg = t("errors.system_busy_generic")

            yield f'data: {json.dumps({"error": error_msg})}\n\n'
            await record_book_error(session, req.book_id, "chat_stream", error_str)
        finally:
            # Only increment usage if stream completed successfully
            if stream_completed:
                await chat_limit_service.increment_usage(current_user, session)
                log_json(logger, logging.INFO, "Chat stream completed successfully", user_id=current_user.id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
