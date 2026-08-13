from app.services.chunking_service import (
    ChunkingService,
    RecursiveCharacterTextSplitter,
)


def test_recursive_splitter_simple():
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=10, chunk_overlap=0, separators=[" "]
    )
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
    assert all(len(c) <= 20 + 5 for c in chunks)  # approximate due to overlap logic


def test_chunking_service_empty():
    service = ChunkingService()
    assert service.split_text("") == []
    assert service.split_text(None) == []


def test_splitter_recursion():
    # Force recursion by using a tiny chunk size and no separators that match until the end
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=5, chunk_overlap=0, separators=["\n", " "]
    )
    text = "word1 word2 word3"
    chunks = splitter.split_text(text)
    assert len(chunks) >= 3
    assert "word1" in chunks[0]


def test_chunking_service_strips_ocr_markers_independently():
    # Defense-in-depth: chunking_service must strip [Header]/[Footer] markers
    # itself, even if the caller forgot to run clean_uyghur_text first (e.g.
    # a marker glued to the end of a content line).
    service = ChunkingService(chunk_size=200, chunk_overlap=0)
    text = "بىرىنچى جۈملە.[Footer] 3\n\nئىككىنچى جۈملە."
    chunks = service.split_text(text)
    joined = " ".join(chunks)
    assert "[Footer]" not in joined
    assert "بىرىنچى جۈملە." in joined
    assert "ئىككىنچى جۈملە." in joined


def test_toc_followed_by_real_content_no_heading_is_kept():
    # A TOC section followed directly by real prose, with no heading in
    # between, must not be silently dropped along with the TOC entries.
    service = ChunkingService(chunk_size=200, chunk_overlap=0)
    text = (
        "# مۇندەرىجە\n\n"
        "1. بىرىنچى باب ..................... 15\n"
        "2. ئىككىنچى باب ..................... 30\n\n"
        "بۇ سۆز باشتىن ئاخىرغىچە داۋاملىشىدۇ. بۇ ھەقىقىي مەزمۇن بولۇپ، "
        "چوقۇم چوقۇم ساقلىنىشى كېرەك، چۈنكى بۇ ھەقىقىي مەزمۇن."
    )
    chunks = service.split_text(text)
    assert chunks, "real content after a TOC must not be dropped entirely"
    joined = " ".join(chunks)
    assert "بۇ سۆز باشتىن ئاخىرغىچە داۋاملىشىدۇ" in joined
    assert "بىرىنچى باب" not in joined  # TOC entries themselves stay dropped


def test_toc_followed_by_heading_still_drops_toc():
    # Existing behavior: a heading after the TOC still ends the skip and the
    # TOC entries are still dropped.
    service = ChunkingService(chunk_size=200, chunk_overlap=0)
    text = (
        "# مۇندەرىجە\n\n"
        "1. بىرىنچى باب ..................... 15\n\n"
        "# بىرىنچى باب\n\n"
        "بۇ سۆز باشتىن ئاخىرغىچە داۋاملىشىدۇ. بۇ ھەقىقىي مەزمۇن بولۇپ، چوقۇم چوقۇم ساقلىنىشى كېرەك."
    )
    chunks = service.split_text(text)
    joined = " ".join(chunks)
    assert "بىرىنچى باب" in joined  # the heading itself is kept
    assert "15" not in joined  # the dot-leader TOC entry is not


def test_merge_splits_overlap():
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=20, chunk_overlap=10, separators=[" "]
    )
    splits = ["This", "is", "a", "test", "with", "overlap"]
    # "This is a test" = 14 chars
    # "test with overlap" = 17 chars
    # overlap "test"
    chunks = splitter._merge_splits(splits, " ")
    assert len(chunks) >= 2
    assert "test" in chunks[0]
    assert "test" in chunks[1]
