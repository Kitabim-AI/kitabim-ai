import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.worker.jobs.llm_spell_check_job import llm_spell_check_job
from app.db.models import Page


@pytest.mark.asyncio
async def test_llm_spell_check_job_success_updates_status_and_text():
    ctx = {}
    mock_session = AsyncMock()
    page = Page(id=1, book_id="book-1", page_number=5, text="original text")
    mock_session.get = AsyncMock(return_value=page)

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.llm_spell_check_job.correct_page_text",
            new_callable=AsyncMock,
        ) as mock_correct,
        patch(
            "services.worker.jobs.llm_spell_check_job.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_correct.return_value = "corrected text"

        mock_repo = MagicMock()
        mock_repo.find_one = AsyncMock(return_value=None)
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        await llm_spell_check_job(ctx, [1])

        assert page.text == "corrected text"
        mock_repo.set_llm_spell_check_status.assert_called_once_with(
            "book-1", 5, "succeeded"
        )
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_llm_spell_check_job_failure_isolated_per_page():
    ctx = {}
    mock_session = AsyncMock()
    page_ok = Page(id=1, book_id="book-1", page_number=5, text="ok text")
    page_fail = Page(id=2, book_id="book-1", page_number=6, text="fail text")

    async def mock_get(model, page_id):
        return page_ok if page_id == 1 else page_fail

    mock_session.get = mock_get

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.llm_spell_check_job.correct_page_text",
            new_callable=AsyncMock,
        ) as mock_correct,
        patch(
            "services.worker.jobs.llm_spell_check_job.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        async def correct_side_effect(text, prev, nxt, config_repo):
            if text == "ok text":
                return "corrected ok text"
            raise ValueError("model failure")

        mock_correct.side_effect = correct_side_effect

        mock_repo = MagicMock()
        mock_repo.find_one = AsyncMock(return_value=None)
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        await llm_spell_check_job(ctx, [1, 2])

        assert page_ok.text == "corrected ok text"
        assert page_fail.text == "fail text"  # untouched on failure

        calls = mock_repo.set_llm_spell_check_status.call_args_list
        assert ("book-1", 5, "succeeded") in [c.args for c in calls]
        assert ("book-1", 6, "failed") in [c.args for c in calls]


@pytest.mark.asyncio
async def test_llm_spell_check_job_bounds_concurrency():
    from app.core.config import settings

    ctx = {}
    mock_session = AsyncMock()
    pages = {
        i: Page(id=i, book_id="book-1", page_number=i, text=f"text {i}")
        for i in range(1, settings.max_parallel_llm_spell_check + 3)
    }

    async def mock_get(model, page_id):
        return pages[page_id]

    mock_session.get = mock_get

    in_flight = 0
    max_in_flight = 0

    async def correct_side_effect(text, prev, nxt, config_repo):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        in_flight -= 1
        return text

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.llm_spell_check_job.correct_page_text",
            side_effect=correct_side_effect,
        ),
        patch(
            "services.worker.jobs.llm_spell_check_job.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_repo = MagicMock()
        mock_repo.find_one = AsyncMock(return_value=None)
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        await llm_spell_check_job(ctx, list(pages.keys()))

        assert max_in_flight <= settings.max_parallel_llm_spell_check
