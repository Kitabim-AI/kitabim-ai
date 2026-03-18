import pytest
from app.services.chunking_service import ChunkingService, RecursiveCharacterTextSplitter

def test_recursive_splitter_simple():
    splitter = RecursiveCharacterTextSplitter(chunk_size=10, chunk_overlap=0, separators=[" "])
    text = "a b c d e f"
    chunks = splitter.split_text(text)
    # "a b c d e " is 10 chars
    assert len(chunks) > 1
    assert "f" in chunks[-1]

def test_chunking_service_basic():
    service = ChunkingService(chunk_size=20, chunk_overlap=5)
    text = "This is a test string for chunking service. It should split this into multiple parts."
    chunks = service.split_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= 20 + 5 for c in chunks) # approximate due to overlap logic

def test_chunking_service_empty():
    service = ChunkingService()
    assert service.split_text("") == []
    assert service.split_text(None) == []

def test_splitter_recursion():
    # Force recursion by using a tiny chunk size and no separators that match until the end
    splitter = RecursiveCharacterTextSplitter(chunk_size=5, chunk_overlap=0, separators=["\n", " "])
    text = "word1 word2 word3"
    chunks = splitter.split_text(text)
    assert len(chunks) >= 3
    assert "word1" in chunks[0]

def test_merge_splits_overlap():
    splitter = RecursiveCharacterTextSplitter(chunk_size=20, chunk_overlap=10, separators=[" "])
    splits = ["This", "is", "a", "test", "with", "overlap"]
    # "This is a test" = 14 chars
    # "test with overlap" = 17 chars
    # overlap "test"
    chunks = splitter._merge_splits(splits, " ")
    assert len(chunks) >= 2
    assert "test" in chunks[0]
    assert "test" in chunks[1]
