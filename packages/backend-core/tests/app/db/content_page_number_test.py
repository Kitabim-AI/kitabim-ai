from app.db.models import Book, Page


def test_page_display_number_default():
    book = Book(id="b1", title="Test Book", content_page_offset=0)
    page = Page(id=1, book_id="b1", page_number=5, book=book)

    assert page.display_page_number == "5"


def test_page_display_number_with_offset():
    book = Book(id="b1", title="Test Book", content_page_offset=12)

    # Page <= offset (front matter) returns physical PDF page number
    page_front = Page(id=1, book_id="b1", page_number=5, book=book)
    assert page_front.display_page_number == "5"

    # Page > offset (content page)
    page_content = Page(id=2, book_id="b1", page_number=13, book=book)
    assert page_content.display_page_number == "1"

    page_content2 = Page(id=3, book_id="b1", page_number=27, book=book)
    assert page_content2.display_page_number == "15"


def test_page_display_number_explicit_override():
    book = Book(id="b1", title="Test Book", content_page_offset=12)

    # Explicit content_page_number overrides offset calculation
    page_roman = Page(
        id=1, book_id="b1", page_number=5, content_page_number="xii", book=book
    )
    assert page_roman.display_page_number == "xii"


def test_extract_standalone_page_number():
    from app.utils.text import extract_standalone_page_number

    assert (
        extract_standalone_page_number("Header Title\n\n- 1 -\n\nPage text content...")
        == 1
    )
    assert extract_standalone_page_number("مەزمۇن...\n\n١٥") == 15
    assert (
        extract_standalone_page_number("No page number anywhere in this text.") is None
    )
