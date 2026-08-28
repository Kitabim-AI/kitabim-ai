import pytest
from unittest.mock import MagicMock, patch
import fitz
from app.services.easyocr_service import ocr_page_with_easyocr, LowConfidenceOcrError


@pytest.mark.asyncio
async def test_ocr_page_with_easyocr_success():
    mock_fitz_page = MagicMock(spec=fitz.Page)
    mock_fitz_page.rect.width = 600
    mock_fitz_page.rect.height = 800
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"fake_image_bytes"
    mock_fitz_page.get_pixmap.return_value = mock_pix

    fake_detection = [
        ([[50, 100], [200, 100], [200, 130], [50, 130]], "سەھىپە مەزمۇنى", 0.95)
    ]

    with (
        patch("app.services.easyocr_service.get_easyocr_reader") as mock_get_reader,
        patch("app.services.easyocr_service._is_blank_image", return_value=False),
        patch(
            "app.services.easyocr_service._preprocess_image", side_effect=lambda b, c: b
        ),
    ):
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = fake_detection
        mock_get_reader.return_value = mock_reader

        result = await ocr_page_with_easyocr(mock_fitz_page)
        assert "سەھىپە مەزمۇنى" in result


@pytest.mark.asyncio
async def test_ocr_page_with_easyocr_low_confidence():
    mock_fitz_page = MagicMock(spec=fitz.Page)
    mock_fitz_page.rect.width = 600
    mock_fitz_page.rect.height = 800
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"fake_image_bytes"
    mock_fitz_page.get_pixmap.return_value = mock_pix

    low_conf_detection = [
        ([[50, 100], [200, 100], [200, 130], [50, 130]], "غۇۋا تېكىست", 0.1)
    ]

    with (
        patch("app.services.easyocr_service.get_easyocr_reader") as mock_get_reader,
        patch("app.services.easyocr_service._is_blank_image", return_value=False),
        patch(
            "app.services.easyocr_service._preprocess_image", side_effect=lambda b, c: b
        ),
    ):
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = low_conf_detection
        mock_get_reader.return_value = mock_reader

        with pytest.raises(LowConfidenceOcrError):
            await ocr_page_with_easyocr(mock_fitz_page, min_confidence=0.5)


@pytest.mark.asyncio
async def test_ocr_page_with_easyocr_blank_page():
    mock_fitz_page = MagicMock(spec=fitz.Page)
    mock_fitz_page.rect.width = 600
    mock_fitz_page.rect.height = 800
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"fake_blank_bytes"
    mock_fitz_page.get_pixmap.return_value = mock_pix

    with (
        patch("app.services.easyocr_service.get_easyocr_reader") as mock_get_reader,
        patch("app.services.easyocr_service._is_blank_image", return_value=True),
        patch(
            "app.services.easyocr_service._preprocess_image", side_effect=lambda b, c: b
        ),
    ):
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = []
        mock_get_reader.return_value = mock_reader

        result = await ocr_page_with_easyocr(mock_fitz_page)
        assert result == ""
