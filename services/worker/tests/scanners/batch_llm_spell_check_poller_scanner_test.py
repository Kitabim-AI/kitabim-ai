import pytest
from unittest.mock import AsyncMock, patch

from services.worker.scanners.batch_llm_spell_check_poller_scanner import (
    run_batch_llm_spell_check_poller_scanner,
)


@pytest.mark.asyncio
async def test_scanner_skips_when_flag_disabled():
    ctx = {}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with (
            patch(
                "services.worker.scanners.batch_llm_spell_check_poller_scanner.SystemConfigsRepository"
            ) as mock_config_cls,
            patch(
                "services.worker.scanners.batch_llm_spell_check_poller_scanner.poll_and_process_batch_llm_spell_check_jobs",
                new_callable=AsyncMock,
            ) as mock_poll,
        ):
            mock_config_repo = AsyncMock()
            mock_config_repo.get_value.return_value = "false"
            mock_config_cls.return_value = mock_config_repo

            await run_batch_llm_spell_check_poller_scanner(ctx)

            mock_poll.assert_not_called()


@pytest.mark.asyncio
async def test_scanner_polls_when_flag_enabled():
    ctx = {}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with (
            patch(
                "services.worker.scanners.batch_llm_spell_check_poller_scanner.SystemConfigsRepository"
            ) as mock_config_cls,
            patch(
                "services.worker.scanners.batch_llm_spell_check_poller_scanner.poll_and_process_batch_llm_spell_check_jobs",
                new_callable=AsyncMock,
            ) as mock_poll,
        ):
            mock_config_repo = AsyncMock()
            mock_config_repo.get_value.return_value = "true"
            mock_config_cls.return_value = mock_config_repo
            mock_poll.return_value = 2

            await run_batch_llm_spell_check_poller_scanner(ctx)

            mock_poll.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_scanner_exception_logged_not_raised():
    ctx = {}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = Exception(
            "Database error"
        )

        # Scanner must catch the exception and log, not raise.
        await run_batch_llm_spell_check_poller_scanner(ctx)
