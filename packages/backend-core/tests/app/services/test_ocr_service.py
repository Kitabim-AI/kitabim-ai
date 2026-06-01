import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.ocr_service import ocr_page_with_gemini, ocr_page_with_easyocr, ocr_page

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
async def test_ocr_page_with_easyocr_success():
    mock_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"image_data"
    mock_page.get_pixmap.return_value = mock_pix
    
    with patch("app.services.ocr_service.httpx.AsyncClient") as mock_client_class, \
         patch("app.services.ocr_service.clean_uyghur_text") as mock_clean:
        
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"text": "raw easyocr text"}
        mock_client.post = AsyncMock(return_value=mock_response)
        
        # Mock context manager of AsyncClient
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_clean.return_value = "clean easyocr text"
        
        text = await ocr_page_with_easyocr(mock_page)
        
        assert text == "clean easyocr text"
        mock_client.post.assert_called_once()
        mock_clean.assert_called_with("raw easyocr text")

@pytest.mark.asyncio
async def test_ocr_page():
    mock_page = MagicMock()
    with patch("app.services.ocr_service.ocr_page_with_gemini", new_callable=AsyncMock) as mock_gemini, \
         patch("app.services.ocr_service.ocr_page_with_easyocr", new_callable=AsyncMock) as mock_easyocr:
        
        mock_gemini.return_value = "gemini text"
        mock_easyocr.return_value = "easyocr text"
        
        # Test default/gemini provider
        result_gemini = await ocr_page(mock_page, "Title", 1, provider="gemini", model_name="test-model")
        assert result_gemini == "gemini text"
        mock_gemini.assert_called_once_with(mock_page, model_name="test-model")
        
        # Test easyocr provider
        result_easyocr = await ocr_page(mock_page, "Title", 1, provider="easyocr")
        assert result_easyocr == "easyocr text"
        mock_easyocr.assert_called_once_with(mock_page)
