import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.ocr_service import ocr_page_with_gemini, _build_ocr_prompt


@pytest.mark.asyncio
async def test_ocr_page_with_gemini_success():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"image_data"
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch(
            "app.services.ocr_service.generate_text_with_image", new_callable=AsyncMock
        ) as mock_gen,
        patch("app.services.ocr_service.clean_uyghur_text") as mock_clean,
        patch(
            "app.services.ocr_service._build_ocr_prompt", new_callable=AsyncMock
        ) as mock_prompt,
    ):
        mock_gen.return_value = "raw text"
        mock_clean.return_value = "clean text"
        mock_prompt.return_value = "built prompt"

        text = await ocr_page_with_gemini(mock_page)

        assert text == "clean text"
        mock_gen.assert_called_once_with(
            "built prompt", b"image_data", "gemini-2.0-flash", timeout=None
        )
        mock_clean.assert_called_with("raw text")


@pytest.mark.asyncio
async def test_ocr_page_with_gemini_retry():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"image_data"
    mock_page.get_pixmap.return_value = mock_pix

    with (
        patch(
            "app.services.ocr_service.generate_text_with_image", new_callable=AsyncMock
        ) as mock_gen,
        patch("app.services.ocr_service.settings") as mock_settings,
        patch(
            "app.services.ocr_service.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep,
        patch(
            "app.services.ocr_service._build_ocr_prompt", new_callable=AsyncMock
        ) as mock_prompt,
    ):
        mock_settings.ocr_max_retries = 2
        mock_prompt.return_value = "built prompt"
        # First call fails with 429, second succeeds
        mock_gen.side_effect = [Exception("429 Resource Exhausted"), "success text"]

        text = await ocr_page_with_gemini(mock_page)

        assert text == "success text"
        assert mock_gen.call_count == 2
        mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_build_ocr_prompt_formats_frequent_corrections():
    mock_session = AsyncMock()
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_session

    with (
        patch("app.services.ocr_service.db_session") as mock_db_session,
        patch("app.services.ocr_service.AutoCorrectRulesRepository") as mock_repo_cls,
    ):
        mock_db_session.async_session_factory.return_value = mock_session_cm
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_frequent_corrections_block = AsyncMock(
            return_value="ئولار -> ئۇلار"
        )

        prompt = await _build_ocr_prompt()

        mock_repo_cls.assert_called_once_with(mock_session)
        assert "ئولار -> ئۇلار" in prompt
        assert "{frequent_corrections}" not in prompt
