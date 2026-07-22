import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.worker.scanners.chunking_scanner import run_chunking_scanner

CONFIG_PATCH_PATH = "services.worker.scanners.chunking_scanner.SystemConfigsRepository"


def _config_side_effect(spell_check_enabled="false", scanner_page_limit="100"):
    def side_effect(key, default=None):
        if key == "spell_check_enabled":
            return spell_check_enabled
        if key == "scanner_page_limit":
            return scanner_page_limit
        return default

    return side_effect


@pytest.mark.asyncio
async def test_chunking_scanner_dispatches_job_for_idle_pages():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}
    mock_session = AsyncMock()

    mock_claim_result = MagicMock()
    mock_claim_result.fetchall.return_value = [(1, "book-1"), (2, "book-1")]
    mock_session.execute.side_effect = [
        mock_claim_result,  # claim SELECT
        MagicMock(),  # UPDATE Page -> in_progress
    ]

    with (
        patch("app.db.session.async_session_factory") as mock_factory,
        patch(CONFIG_PATCH_PATH) as mock_config_cls,
        patch(
            "services.worker.scanners.chunking_scanner.BookMilestoneService.update_book_milestone_for_step",
            new_callable=AsyncMock,
        ) as mock_update_milestone,
    ):
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(
            side_effect=_config_side_effect()
        )

        await run_chunking_scanner(ctx)

    mock_redis.enqueue_job.assert_called_once_with("chunking_job", page_ids=[1, 2])
    mock_update_milestone.assert_called_once_with(mock_session, "book-1", "chunking")


@pytest.mark.asyncio
async def test_chunking_scanner_no_idle_pages():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    mock_empty = MagicMock()
    mock_empty.fetchall.return_value = []
    mock_session.execute.return_value = mock_empty

    with (
        patch("app.db.session.async_session_factory") as mock_factory,
        patch(CONFIG_PATCH_PATH) as mock_config_cls,
    ):
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(
            side_effect=_config_side_effect()
        )

        await run_chunking_scanner(ctx)

    ctx["redis"].enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_chunking_scanner_requires_spell_check_done_when_enabled():
    """When spell_check is enabled, the claim query must also filter on
    spell_check_milestone in ('succeeded', 'failed') — verified via the
    compiled SQL since the DB itself enforces the actual filtering."""
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    mock_empty = MagicMock()
    mock_empty.fetchall.return_value = []
    mock_session.execute.return_value = mock_empty

    with (
        patch("app.db.session.async_session_factory") as mock_factory,
        patch(CONFIG_PATCH_PATH) as mock_config_cls,
    ):
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(
            side_effect=_config_side_effect(spell_check_enabled="true")
        )

        await run_chunking_scanner(ctx)

    claim_stmt = mock_session.execute.call_args_list[0].args[0]
    compiled = str(claim_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "spell_check_milestone" in compiled
    assert "succeeded" in compiled and "failed" in compiled


@pytest.mark.asyncio
async def test_chunking_scanner_omits_spell_check_filter_when_disabled():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    mock_empty = MagicMock()
    mock_empty.fetchall.return_value = []
    mock_session.execute.return_value = mock_empty

    with (
        patch("app.db.session.async_session_factory") as mock_factory,
        patch(CONFIG_PATCH_PATH) as mock_config_cls,
    ):
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_config_cls.return_value.get_value = AsyncMock(
            side_effect=_config_side_effect(spell_check_enabled="false")
        )

        await run_chunking_scanner(ctx)

    claim_stmt = mock_session.execute.call_args_list[0].args[0]
    compiled = str(claim_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "spell_check_milestone" not in compiled
