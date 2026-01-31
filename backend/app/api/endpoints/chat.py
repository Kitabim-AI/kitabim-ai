from fastapi import APIRouter, HTTPException

from app.db.mongodb import db_manager
from app.models.schemas import ChatRequest, ChatResponse
from app.services.rag_service import rag_service

router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat_with_book_api(req: ChatRequest):
    db = db_manager.db
    try:
        answer = await rag_service.answer_question(req, db)
        return {"answer": answer}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI Assistant Error: {exc}")
