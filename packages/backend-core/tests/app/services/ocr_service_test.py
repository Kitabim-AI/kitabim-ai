import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.ocr_service import ocr_page_with_gemini, ocr_page

@pytest.mark.asyncio
async def test_ocr_page_with_gemini_success():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"image_data"
    mock_page.get_pixmap.return_value = mock_pix
    
    with patch("app.services.ocr_service.generate_text_with_image", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.ocr_service.clean_uyghur_text") as mock_clean:
        
        mock_gen.return_value = "raw text"
        mock_clean.return_value = "clean text"
        
        text = await ocr_page_with_gemini(mock_page)
        
        assert text == "clean text"
        mock_gen.assert_called_once()
        mock_clean.assert_called_with("raw text")

@pytest.mark.asyncio
async def test_ocr_page_with_gemini_retry():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"image_data"
    mock_page.get_pixmap.return_value = mock_pix
    
    with patch("app.services.ocr_service.generate_text_with_image", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.ocr_service.settings") as mock_settings, \
         patch("app.services.ocr_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        
        mock_settings.ocr_max_retries = 2
        # First call fails with 429, second succeeds
        mock_gen.side_effect = [Exception("429 Resource Exhausted"), "success text"]
        
        text = await ocr_page_with_gemini(mock_page)
        
        assert text == "success text"
        assert mock_gen.call_count == 2
        mock_sleep.assert_called_once()

@pytest.mark.asyncio
async def test_ocr_page():
    mock_page = MagicMock()
    with patch("app.services.ocr_service.ocr_page_with_gemini", new_callable=AsyncMock) as mock_ocr:
        mock_ocr.return_value = "text"
        result = await ocr_page(mock_page, "Title", 1)
        assert result == "text"
        mock_ocr.assert_called_once_with(mock_page)
