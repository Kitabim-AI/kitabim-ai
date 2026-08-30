from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import cli


@pytest.mark.asyncio
async def test_cmd_ocr_renders_and_ocrs_every_page_then_serves(tmp_path: Path):
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    out_dir = tmp_path / "out"

    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 2
    mock_doc.load_page.return_value = "fake-fitz-page"
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"\x89PNG fake"

    with (
        patch("cli.fitz.open", return_value=mock_doc),
        patch("cli.get_recognition_predictor", AsyncMock(return_value="predictor")),
        patch(
            "cli.ocr_page_with_surya",
            AsyncMock(side_effect=["text one", "text two"]),
        ),
        patch("cli.render_page_png", return_value=b"\x89PNG fake"),
        patch("cli.serve") as mock_serve,
    ):
        await cli.cmd_ocr(pdf_path, out_dir, open_preview=True)

    from engine.workdir import OcrWorkDir

    wd = OcrWorkDir.load(out_dir)
    assert wd.total_pages == 2
    assert wd.get_page(1).text == "text one"
    assert wd.get_page(2).text == "text two"
    mock_serve.assert_called_once()


@pytest.mark.asyncio
async def test_cmd_ocr_flags_failed_page_and_continues(tmp_path: Path):
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    out_dir = tmp_path / "out"

    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 2
    mock_doc.load_page.return_value = "fake-fitz-page"

    from engine.recognize import LowConfidenceOcrError

    with (
        patch("cli.fitz.open", return_value=mock_doc),
        patch("cli.get_recognition_predictor", AsyncMock(return_value="predictor")),
        patch(
            "cli.ocr_page_with_surya",
            AsyncMock(side_effect=[LowConfidenceOcrError("bad page"), "text two"]),
        ),
        patch("cli.render_page_png", return_value=b"\x89PNG fake"),
        patch("cli.serve") as mock_serve,
    ):
        await cli.cmd_ocr(pdf_path, out_dir, open_preview=True)

    from engine.workdir import OcrWorkDir

    wd = OcrWorkDir.load(out_dir)
    assert wd.get_page(1).status == "failed"
    assert "bad page" in wd.get_page(1).error
    assert wd.get_page(2).text == "text two"
    mock_serve.assert_called_once()  # one bad page doesn't abort the whole run


@pytest.mark.asyncio
async def test_cmd_correct_seeds_workdir_from_existing_book_pages(tmp_path: Path):
    out_dir = tmp_path / "out"
    mock_client = MagicMock()
    mock_client.download_book_pdf.return_value = tmp_path / "downloaded.pdf"
    mock_client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "existing one", "isToc": False},
        {"pageNumber": 2, "text": "existing two", "isToc": True},
    ]
    (tmp_path / "downloaded.pdf").write_bytes(b"%PDF-fake")

    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 2

    with (
        patch("cli.KitabimClient", return_value=mock_client),
        patch("cli.fitz.open", return_value=mock_doc),
        patch("cli.render_page_png", return_value=b"\x89PNG fake"),
        patch("cli.serve") as mock_serve,
    ):
        await cli.cmd_correct(
            "book123", out_dir, base_url="http://localhost:8000", open_preview=True
        )

    from engine.workdir import OcrWorkDir

    wd = OcrWorkDir.load(out_dir)
    assert wd.book_id == "book123"
    assert wd.get_page(1).text == "existing one"
    assert wd.get_page(2).is_toc is True
    mock_serve.assert_called_once()


def test_build_parser_ocr_command():
    parser = cli.build_parser()
    args = parser.parse_args(["ocr", "book.pdf", "--out", "workdir"])
    assert args.command == "ocr"
    assert args.pdf == "book.pdf"
    assert args.out == "workdir"


def test_build_parser_correct_command():
    parser = cli.build_parser()
    args = parser.parse_args(
        ["correct", "book123", "--out", "workdir", "--base-url", "http://x"]
    )
    assert args.command == "correct"
    assert args.book_id == "book123"
    assert args.out == "workdir"
    assert args.base_url == "http://x"
