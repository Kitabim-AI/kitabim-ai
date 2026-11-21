import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def _mock_admin():
    from app.models.user import User, UserRole

    return User(
        id="admin-1",
        email="admin@example.com",
        display_name="Admin",
        role=UserRole.ADMIN,
        provider="google",
        provider_id="admin-1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def _make_submission(**overrides):
    from app.db.models import ContactSubmission

    now = datetime(2026, 11, 14, 20, 27, tzinfo=timezone.utc)
    defaults = {
        "id": 1,
        "name": "SecTest_ContactRateLimit",
        "email": "sectest@example.com",
        "interest": "other",
        "message": "Authorized security test: verifying absence of rate limiting",
        "status": "new",
        "admin_notes": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "created_at": now,
    }
    defaults.update(overrides)
    return ContactSubmission(**defaults)


@pytest.mark.asyncio
async def test_get_contact_submission_found():
    setup_paths()
    from api.endpoints.contact_router import get_contact_submission

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = _make_submission(id=7)
    mock_session.execute.return_value = mock_res

    result = await get_contact_submission(
        submission_id=7, current_user=_mock_admin(), session=mock_session
    )
    assert result.id == 7
    assert result.email == "sectest@example.com"


@pytest.mark.asyncio
async def test_get_contact_submission_not_found():
    setup_paths()
    from api.endpoints.contact_router import get_contact_submission

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc_info:
        await get_contact_submission(
            submission_id=404, current_user=_mock_admin(), session=mock_session
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_contact_submission_status_and_notes():
    setup_paths()
    from api.endpoints.contact_router import update_contact_submission
    from app.models.schemas import ContactSubmissionUpdate

    now = datetime(2026, 11, 19, 21, 0, tzinfo=timezone.utc)
    updated_model = _make_submission(
        id=1,
        status="archived",
        admin_notes="Security audit test submission",
        reviewed_by="admin-1",
        reviewed_at=now,
    )

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = updated_model
    mock_session.execute.return_value = mock_res

    payload = ContactSubmissionUpdate.model_validate(
        {"status": "archived", "adminNotes": "Security audit test submission"}
    )
    result = await update_contact_submission(
        submission_id=1,
        payload=payload,
        current_user=_mock_admin(),
        session=mock_session,
    )

    assert result.status == "archived"
    assert result.admin_notes == "Security audit test submission"
    assert result.reviewed_by == "admin-1"
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_contact_submission_empty_payload_rejected():
    setup_paths()
    from api.endpoints.contact_router import update_contact_submission
    from app.models.schemas import ContactSubmissionUpdate

    mock_session = AsyncMock()
    payload = ContactSubmissionUpdate.model_validate({})

    with pytest.raises(HTTPException) as exc_info:
        await update_contact_submission(
            submission_id=1,
            payload=payload,
            current_user=_mock_admin(),
            session=mock_session,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_contact_submission_success():
    setup_paths()
    from api.endpoints.contact_router import delete_contact_submission

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 1
    mock_session.execute.return_value = mock_res

    response = await delete_contact_submission(
        submission_id=1, current_user=_mock_admin(), session=mock_session
    )
    assert response.status_code == 204
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_contact_submission_not_found():
    setup_paths()
    from api.endpoints.contact_router import delete_contact_submission

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 0
    mock_session.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc_info:
        await delete_contact_submission(
            submission_id=999, current_user=_mock_admin(), session=mock_session
        )
    assert exc_info.value.status_code == 404
