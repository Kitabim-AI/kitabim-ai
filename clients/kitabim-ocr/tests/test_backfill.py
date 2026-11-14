from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import pytest

import backfill
from engine.recognize import LowConfidenceOcrError, PageOcrResult


def _create_sample_pdf(path: Path, num_pages: int = 4) -> None:
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page(width=200, height=200)
    doc.save(path)
    doc.close()


def test_has_formatted_pipe_toc():
    assert (
        backfill.has_formatted_pipe_toc(
            "| بىرىنچى باب | 3 |\n| ئىككىنچى باب | 15 |", min_rows=2
        )
        is True
    )
    assert backfill.has_formatted_pipe_toc("| بىرىنچى باب | 3 |", min_rows=2) is False
    assert (
        backfill.has_formatted_pipe_toc(
            "1. بىرىنچى باب ....... 3\n2. ئىككىنچى باب ....... 15"
        )
        is False
    )


@pytest.mark.asyncio
async def test_backfill_single_book_skips_cover_and_formatted_toc_and_dehyphenates(
    tmp_path: Path,
):
    client = MagicMock()

    def _fake_download(book_id: str, dest: Path):
        _create_sample_pdf(dest, num_pages=4)
        return dest

    client.download_book_pdf.side_effect = _fake_download
    client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "Cover text", "isToc": False},
        {
            "pageNumber": 2,
            "text": "مۇندەرىجە\n| باب بىر | 1 |\n| باب ئىككى | 10 |",
            "isToc": True,
        },
        {"pageNumber": 3, "text": "Old p3", "isToc": False},
        {"pageNumber": 4, "text": "Old p4", "isToc": False},
    ]
    client.replace_book_ocr.return_value = {
        "pagesUpdated": 2,
        "pagesUnchanged": 2,
        "backupUri": "gs://bucket/backup.json.gz",
    }

    async def _fake_ocr_with_meta(fitz_page, predictor, **kwargs):
        pno = fitz_page.number + 1
        if pno == 3:
            return PageOcrResult(
                text="# باب بىر\n\nبۇ تەتقى-",
                detected_page_number=1,
                ended_with_hyphen=True,
            )
        if pno == 4:
            return PageOcrResult(
                text="قاتلار مۇھىم.",
                detected_page_number=2,
                ended_with_hyphen=False,
            )
        raise AssertionError(f"Unexpected OCR call for page {pno}")

    audit_log = tmp_path / "backfill_audit.jsonl"
    with (
        patch("backfill.get_recognition_predictor", new=AsyncMock(return_value="pred")),
        patch("backfill.ocr_page_with_meta", side_effect=_fake_ocr_with_meta),
    ):
        entry = await backfill.backfill_single_book(
            "book-1",
            client,
            tmp_path,
            title="Test Book",
            audit_log_path=audit_log,
        )

    assert entry["ocrd_pages"] == 2
    assert entry["skipped_pages"] == 2
    assert entry["failed_pages"] == 0
    assert entry["dehyphenated_pairs"] == 1

    # Verify temporary directory was cleaned up
    assert not list(tmp_path.glob("backfill-book-1-*"))

    # Verify replace_book_ocr payload
    sent_pages = client.replace_book_ocr.call_args.args[1]
    assert len(sent_pages) == 4
    assert sent_pages[0].skipped is True  # page 1 cover
    assert sent_pages[1].skipped is True  # page 2 pipe ToC
    assert sent_pages[2].skipped is False
    assert sent_pages[2].text == "# باب بىر\n\nبۇ تەتقىقاتلار"
    assert sent_pages[2].detected_page_number == 1
    assert sent_pages[3].text == "مۇھىم."
    assert sent_pages[3].detected_page_number == 2

    # Verify audit log written
    logged = json.loads(audit_log.read_text(encoding="utf-8").strip())
    assert logged["book_id"] == "book-1"
    assert logged["backup_uri"] == "gs://bucket/backup.json.gz"


@pytest.mark.asyncio
async def test_backfill_single_book_reocrs_unformatted_toc_and_marks_failed_pages_skipped(
    tmp_path: Path,
):
    client = MagicMock()
    client.download_book_pdf.side_effect = lambda b, dest: _create_sample_pdf(
        dest, num_pages=3
    )
    client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "Cover", "isToc": False},
        {"pageNumber": 2, "text": "مۇندەرىجە\nباب بىر .... 1", "isToc": True},
        {"pageNumber": 3, "text": "Existing body page 3", "isToc": False},
    ]
    client.replace_book_ocr.return_value = {"pagesUpdated": 1, "pagesUnchanged": 2}

    async def _fake_ocr(fitz_page, predictor, **kwargs):
        pno = fitz_page.number + 1
        if pno == 2:
            return PageOcrResult(
                text="## مۇندەرىجە\n\n| باب بىر | 1 |\n| باب ئىككى | 5 |",
                detected_page_number=None,
                ended_with_hyphen=False,
            )
        raise LowConfidenceOcrError("blurry scan")

    with (
        patch("backfill.get_recognition_predictor", new=AsyncMock(return_value="pred")),
        patch("backfill.ocr_page_with_meta", side_effect=_fake_ocr),
    ):
        entry = await backfill.backfill_single_book("book-2", client, tmp_path)

    assert entry["ocrd_pages"] == 1
    assert entry["failed_pages"] == 1
    sent_pages = client.replace_book_ocr.call_args.args[1]
    # Unformatted ToC page 2 was re-OCR'd
    assert sent_pages[1].skipped is False
    assert "| باب بىر | 1 |" in sent_pages[1].text
    # Failed page 3 fell back to skipped=True preserving existing text
    assert sent_pages[2].skipped is True
    assert sent_pages[2].text == "Existing body page 3"


@pytest.mark.asyncio
async def test_run_backfill_throttles_on_server_backlog_and_supports_dry_run(
    tmp_path: Path,
):
    client = MagicMock()
    client.get_backfill_candidates.side_effect = [
        {
            "candidates": [{"id": "b1", "title": "Book 1", "totalPages": 10}],
            "activePipelineBookCount": 3,
        },
        {
            "candidates": [{"id": "b1", "title": "Book 1", "totalPages": 10}],
            "activePipelineBookCount": 1,
        },
        {"candidates": [], "activePipelineBookCount": 0},
    ]

    with (
        patch(
            "backfill.backfill_single_book",
            new=AsyncMock(return_value={"book_id": "b1", "ocrd_pages": 9}),
        ) as mock_single,
        patch("asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        results = await backfill.run_backfill(
            client,
            tmp_path,
            max_server_backlog=3,
            poll_interval=0.01,
        )

    assert len(results) == 1
    assert results[0]["book_id"] == "b1"
    mock_sleep.assert_awaited_once_with(0.01)
    mock_single.assert_awaited_once()

    # Dry run mode should never invoke backfill_single_book
    client.get_backfill_candidates.side_effect = [
        {
            "candidates": [{"id": "b2", "title": "Book 2", "totalPages": 20}],
            "activePipelineBookCount": 0,
        }
    ]
    with patch("backfill.backfill_single_book", new=AsyncMock()) as mock_dry_single:
        dry_res = await backfill.run_backfill(client, tmp_path, dry_run=True)

    assert len(dry_res) == 1
    assert dry_res[0]["dry_run"] is True
    mock_dry_single.assert_not_awaited()
