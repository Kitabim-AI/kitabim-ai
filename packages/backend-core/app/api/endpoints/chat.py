import logging
from fastapi import APIRouter, Depends, HTTPException

from app.db.mongodb import db_manager
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
    db = db_manager.db
    try:
        answer = await rag_service.answer_question(req, db)
        return {"answer": answer}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log_json(logger, logging.ERROR, "Chat request failed", book_id=req.bookId, error=str(exc))
        await record_book_error(db, req.bookId, "chat", str(exc))
        raise HTTPException(status_code=500, detail=f"AI Assistant Error: {exc}")
