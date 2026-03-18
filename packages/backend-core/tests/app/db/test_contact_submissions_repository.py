import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from app.db.repositories.contact_submissions import ContactSubmissionsRepository, get_contact_submissions_repository
from app.db.models import ContactSubmission

@pytest.mark.asyncio
async def test_create_submission():
    session = AsyncMock()
    session.add = MagicMock()
    repo = ContactSubmissionsRepository(session)
    
    # Mock refresh to avoid errors
    session.refresh = AsyncMock()
    
    submission = await repo.create_submission(
        name="Test User",
        email="test@example.com",
        interest="Feedback",
        message="Hello"
    )
    
    assert submission.name == "Test User"
    assert submission.status == "new"
    assert session.add.called
    assert session.flush.called
    assert session.refresh.called

@pytest.mark.asyncio
async def test_find_many_contact_submissions():
    session = AsyncMock()
    repo = ContactSubmissionsRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [ContactSubmission(id=1, name="U1")]
    session.execute.return_value = mock_res
    
    res = await repo.find_many(status="new", skip=0, limit=10)
    assert len(res) == 1
    assert res[0].name == "U1"
    assert session.execute.called

@pytest.mark.asyncio
async def test_count_contact_submissions():
    session = AsyncMock()
    repo = ContactSubmissionsRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 5
    session.execute.return_value = mock_res
    
    count = await repo.count(status="new")
    assert count == 5

def test_get_contact_submissions_repository():
    session = MagicMock()
    repo = get_contact_submissions_repository(session)
    assert isinstance(repo, ContactSubmissionsRepository)
