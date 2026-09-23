from app.db.models import Page, Book


def test_models_basic():
    """Basic unit test scaffold for models."""
    assert True


def test_page_model_strips_null_bytes():
    page = Page(
        book_id="book-1", page_number=1, text="hello\x00world\x00", error="err\x00"
    )
    assert page.text == "helloworld"
    assert page.error == "err"


def test_book_model_strips_null_bytes():
    book = Book(id="b1", title="Title\x00", author="Author\x00", last_error="Err\x00")
    assert book.title == "Title"
    assert book.author == "Author"
    assert book.last_error == "Err"
