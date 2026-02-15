import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession


from app.db.session import get_session
from app.models.schemas import ChatRequest, ChatResponse
from app.models.user import User
from app.services.rag_service import rag_service
from app.utils.errors import record_book_error
from app.utils.observability import log_json
from app.auth.dependencies import require_reader

router = APIRouter()
logger = logging.getLogger("app.chat")


@router.post("/", response_model=ChatResponse)
async def chat_with_book_api(
    req: ChatRequest,
    current_user: User = Depends(require_reader),
    session: AsyncSession = Depends(get_session),
):
    """Chat with book using RAG with SQLAlchemy"""
    try:
        # Pass session for all DB operations
        answer = await rag_service.answer_question(req, session)
        return {"answer": answer}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log_json(logger, logging.ERROR, "Chat request failed", book_id=req.book_id, error=str(exc))
        # Record error using SQLAlchemy
        await record_book_error(session, req.book_id, "chat", str(exc))
        raise HTTPException(status_code=500, detail=f"AI Assistant Error: {exc}")
