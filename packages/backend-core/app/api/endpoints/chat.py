import logging
from fastapi import APIRouter, Depends, HTTPException

from app.db.postgres import db_manager, get_chunks_repo
from app.db.postgres_helpers import pg_db
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
):
    try:
        # Use PostgreSQL for RAG - pass the db_manager for vector search
        answer = await rag_service.answer_question(req, db_manager, pg_db)
        return {"answer": answer}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log_json(logger, logging.ERROR, "Chat request failed", book_id=req.bookId, error=str(exc))
        # Record error using PostgreSQL
        await record_book_error(pg_db, req.bookId, "chat", str(exc))
        raise HTTPException(status_code=500, detail=f"AI Assistant Error: {exc}")
