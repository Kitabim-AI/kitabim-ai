import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.pdf_service import read_pdf_page_count, extract_pdf_cover, create_page_stubs
from app.services.docx_service import _load_footnotes, _is_heading_para, extract_docx_pages, extract_docx_cover
from app.db.models import Page

# PDF Service Tests
def test_read_pdf_page_count():
    with patch("fitz.open") as mock_open:
        mock_doc = mock_open.return_value
        mock_doc.__len__.return_value = 5
        
        count = read_pdf_page_count(Path("test.pdf"))
        assert count == 5
        mock_doc.close.called

def test_read_pdf_page_count_fail():
    with patch("fitz.open", side_effect=Exception("fail")):
        assert read_pdf_page_count(Path("test.pdf")) == 0

def test_extract_pdf_cover():
    with patch("fitz.open") as mock_open:
        mock_doc = mock_open.return_value
        mock_doc.__len__.return_value = 1
        mock_page = mock_doc.load_page.return_value
        mock_pix = mock_page.get_pixmap.return_value
        
        res = extract_pdf_cover(Path("test.pdf"), Path("cover.jpg"))
        assert res is True
        assert mock_pix.save.called

@pytest.mark.asyncio
async def test_create_page_stubs():
    session = MagicMock()
    create_page_stubs(session, "book1", 3)
    assert session.add_all.called
    pages = session.add_all.call_args[0][0]
    assert len(pages) == 3
    assert pages[0].page_number == 1

# Docx Service Tests
def test_load_footnotes_no_file(tmp_path):
    docx = tmp_path / "test.docx"
    import zipfile
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("test.txt", "data")
    
    res = _load_footnotes(docx)
    assert res == {}

def test_is_heading_para():
    para = MagicMock()
    # No runs
    para.findall.return_value = []
    assert _is_heading_para(para) is False
    
    # Bold para
    run = MagicMock()
    run.findall.return_value = [MagicMock(text="Title")]
    run.find.return_value = MagicMock() # w:b
    para.findall.return_value = [run]
    assert _is_heading_para(para) is True

@pytest.mark.asyncio
async def test_extract_docx_pages_fallback():
    with patch("docx.Document") as mock_doc_cls:
        mock_doc = mock_doc_cls.return_value
        
        # Mock a paragraph with a single run having text
        mock_para = MagicMock()
        mock_para.text = "Some text"
        
        mock_run = MagicMock()
        mock_run.find.return_value = MagicMock(text="Some text") # find w:t
        mock_run.get.return_value = None # no footnote
        
        import app.services.docx_service as ds
        # w:r
        para_el = MagicMock()
        para_el.findall.return_value = [mock_run]
        mock_para._p = para_el
        
        mock_doc.paragraphs = [mock_para]
        
        with patch("app.services.docx_service._load_footnotes", return_value={}):
            pages = extract_docx_pages(Path("test.docx"))
            # Should have 1 page containing "Some text"
            assert len(pages) == 1
            assert "Some text" in pages[0]

@pytest.mark.asyncio
async def test_extract_docx_cover():
    with patch("docx.Document") as mock_doc_cls:
        mock_doc = mock_doc_cls.return_value
        mock_rel = MagicMock()
        mock_rel.reltype = "image"
        mock_rel.target_part.blob = b"fake-image"
        mock_doc.part.rels = {"rId1": mock_rel}
        
        res = extract_docx_cover(Path("test.docx"), Path("cover.jpg"))
        assert res is True
