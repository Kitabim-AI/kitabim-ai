import fitz
import pytest

from engine.page_layout import count_logical_pages, is_spread_page, resolve_logical_page


def _doc_with_pages(*sizes: tuple[float, float]) -> fitz.Document:
    doc = fitz.open()
    for width, height in sizes:
        doc.new_page(width=width, height=height)
    return doc


def test_is_spread_page_detects_wide_pages():
    doc = _doc_with_pages((400, 600), (800, 600))
    assert is_spread_page(doc.load_page(0)) is False
    assert is_spread_page(doc.load_page(1)) is True


def test_count_logical_pages_splits_spreads_only():
    # portrait, spread, portrait -> 1 + 2 + 1
    doc = _doc_with_pages((400, 600), (800, 600), (400, 600))
    assert count_logical_pages(doc) == 4


def test_count_logical_pages_with_no_spreads_matches_pdf_page_count():
    doc = _doc_with_pages((400, 600), (400, 600))
    assert count_logical_pages(doc) == 2


def test_resolve_logical_page_maps_normal_pages_with_no_clip():
    doc = _doc_with_pages((400, 600), (400, 600))
    page, clip = resolve_logical_page(doc, 1)
    assert page.number == 0
    assert clip is None

    page, clip = resolve_logical_page(doc, 2)
    assert page.number == 1
    assert clip is None


def test_resolve_logical_page_splits_spread_right_half_is_lower_page_number():
    # Uyghur is RTL: within a spread, the right (higher-x) half is the
    # lower/earlier logical page, matching how the book was bound and
    # scanned.
    doc = _doc_with_pages((400, 600), (800, 600), (400, 600))

    page, clip = resolve_logical_page(doc, 2)
    assert page.number == 1
    assert clip.x0 == 400 and clip.x1 == 800  # right half

    page, clip = resolve_logical_page(doc, 3)
    assert page.number == 1
    assert clip.x0 == 0 and clip.x1 == 400  # left half

    page, clip = resolve_logical_page(doc, 4)
    assert page.number == 2
    assert clip is None


def test_resolve_logical_page_out_of_range_raises():
    doc = _doc_with_pages((400, 600))
    with pytest.raises(IndexError):
        resolve_logical_page(doc, 2)
