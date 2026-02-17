import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession


from app.db.session import get_session
from app.models.schemas import ChatRequest, ChatResponse, ChatUsageStatus
from app.models.user import User
from app.services.rag_service import rag_service
from app.services.chat_limit_service import chat_limit_service
from app.utils.errors import record_book_error
from app.utils.observability import log_json
from app.auth.dependencies import require_reader

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
            detail="كەچۈرۈڭ، سىزنىڭ كۈندىلىك پاراڭلىشىش چەكلىمىڭىز توشتى. ئەتە قايتا سىناپ بېقىڭ." # Daily limit reached Uyghur
        )

    try:
        # 2. Process chat request
        answer = await rag_service.answer_question(req, session, user_id=current_user.id)
        
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
                detail="كەچۈرۈڭ، نۆۋەتتە سىستېما ئالدىراش، سەل تۇرۇپ قايتا سىناپ بېقىڭ." # System busy (Quota)
            )
            
        # Record error using SQLAlchemy
        await record_book_error(session, req.book_id, "chat", error_str)
        raise HTTPException(status_code=500, detail=f"AI Assistant Error: {exc}")
