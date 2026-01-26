import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import lifespan
from fastapi import FastAPI

@pytest.mark.asyncio
async def test_lifespan_resume_logic(mock_db):
    # Setup mock books that need resume
    mock_db.books.find.return_value.to_list.return_value = [
        {"_id": "oid1", "status": "processing", "title": "T1", "author": "A1", "uploadDate": datetime.now()},
        {"id": "book2", "status": "ready", "coverUrl": None, "title": "T2", "author": "A2", "uploadDate": datetime.now()}
    ]
    
    app = FastAPI()
    with patch("app.main.db_manager.connect_to_storage", AsyncMock()), \
         patch("app.main.db_manager.close_storage", AsyncMock()), \
         patch("app.main.process_pdf_task") as mock_task:
        
        async with lifespan(app):
            # Wait a bit for tasks to be created
            pass
        
        # Check if process_pdf_task was called for both books
        assert mock_task.call_count == 2
