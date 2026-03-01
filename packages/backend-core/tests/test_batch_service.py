"""
Test Batch Service Integration.

Run with: pytest packages/backend-core/tests/test_batch_service.py -v
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models import Page, Chunk, BatchJob
from app.db.session import get_database_url
from app.services.batch_service import BatchService


@pytest.fixture
async def test_engine():
    """Create test database engine"""
    database_url = get_database_url()
    engine = create_async_engine(database_url, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    """Create test database session"""
    async_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    async with async_session_factory() as session:
        yield session


class TestBatchService:
    """Test suite for BatchService"""

    @pytest.mark.asyncio
    @patch('app.services.batch_service.GeminiBatchClient')
    @patch('app.services.batch_service.storage')
    async def test_submit_ocr_batch_no_pending_pages(
        self, mock_storage, mock_client_cls, test_session
    ):
        """Test OCR batch submission when no pages are pending"""
        service = BatchService(test_session)

        # No pending pages in DB (empty result)
        job_id = await service.submit_ocr_batch(limit=10)

        assert job_id is None

    @pytest.mark.asyncio
    @patch('app.services.batch_service.GeminiBatchClient')
    @patch('app.services.batch_service.storage')
    async def test_submit_embedding_batch_no_chunks(
        self, mock_storage, mock_client_cls, test_session
    ):
        """Test embedding batch submission when no chunks need embeddings"""
        service = BatchService(test_session)

        # No chunks without embeddings
        job_id = await service.submit_embedding_batch(limit=10)

        assert job_id is None

    @pytest.mark.asyncio
    async def test_handle_ocr_result_parsing(self, test_session):
        """Test OCR result parsing logic"""
        service = BatchService(test_session)

        # Create test page
        from app.db.models import Book
        test_book_id = f"test_{uuid4().hex[:8]}"

        book = Book(
            id=test_book_id,
            content_hash=f"hash_{uuid4().hex}",
            title="Test Book",
            author="Test Author",
            total_pages=1,
            status="ocr_processing"
        )
        test_session.add(book)

        page = Page(
            book_id=test_book_id,
            page_number=1,
            status="ocr_processing",
            text=None
        )
        test_session.add(page)
        await test_session.commit()

        # Simulate OCR result
        custom_id = f"ocr_{test_book_id}_1"
        response = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": "This is extracted text from page 1"
                    }]
                }
            }]
        }

        # Handle result
        await service._handle_ocr_result(custom_id, response)
        await test_session.commit()

        # Verify page was updated
        await test_session.refresh(page)
        assert page.text == "This is extracted text from page 1"
        assert page.status == "ocr_done"

        # Cleanup
        await test_session.delete(page)
        await test_session.delete(book)
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_handle_embedding_result_parsing(self, test_session):
        """Test embedding result parsing logic"""
        service = BatchService(test_session)

        # Create test chunk
        from app.db.models import Book
        test_book_id = f"test_{uuid4().hex[:8]}"

        book = Book(
            id=test_book_id,
            content_hash=f"hash_{uuid4().hex}",
            title="Test Book",
            author="Test Author",
            total_pages=1,
            status="ready"
        )
        test_session.add(book)

        page = Page(
            book_id=test_book_id,
            page_number=1,
            status="chunked",
            text="Test text"
        )
        test_session.add(page)

        chunk = Chunk(
            book_id=test_book_id,
            page_number=1,
            chunk_index=0,
            text="Test chunk text",
            embedding=None
        )
        test_session.add(chunk)
        await test_session.commit()

        # Simulate embedding result
        custom_id = f"embed_{chunk.id}"
        response = {
            "embedding": {
                "values": [0.1] * 768  # Mock embedding vector
            }
        }

        # Handle result
        await service._handle_embedding_result(custom_id, response)
        await test_session.commit()

        # Verify chunk was updated
        await test_session.refresh(chunk)
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 768

        # Cleanup
        await test_session.delete(chunk)
        await test_session.delete(page)
        await test_session.delete(book)
        await test_session.commit()

    @pytest.mark.asyncio
    @patch('app.services.batch_service.GeminiBatchClient')
    async def test_poll_and_process_jobs_model_mismatch(
        self, mock_client_cls, test_session
    ):
        """Test model mismatch detection during polling"""
        # Create mock client
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Mock remote job with wrong model
        mock_remote_job = MagicMock()
        mock_remote_job.state = "RUNNING"
        mock_remote_job.model = "models/gemini-1.5-flash"  # Wrong model
        mock_client.get_job.return_value = mock_remote_job

        # Create batch job in DB
        from app.db.repositories.batch_jobs import BatchJobsRepository
        jobs_repo = BatchJobsRepository(test_session)

        job = await jobs_repo.create_job("ocr", 10, "files/test-123")
        job.status = "submitted"
        job.remote_job_id = "batches/test-job-123"
        await test_session.commit()

        # Mock settings to return different model
        with patch('app.services.batch_service.settings') as mock_settings:
            mock_settings.gemini_model_name = "gemini-2.0-flash-exp"
            mock_settings.gemini_embedding_model = "text-embedding-004"

            service = BatchService(test_session)
            await service.poll_and_process_jobs()

        # Job should be failed due to model mismatch
        await test_session.refresh(job)
        assert job.status == "failed"
        assert "Model mismatch" in job.error_message

        # Cleanup
        await test_session.delete(job)
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_chunk_ocr_done_pages(self, test_session):
        """Test chunking of OCR-completed pages"""
        service = BatchService(test_session)

        # Create test book and page
        from app.db.models import Book
        test_book_id = f"test_{uuid4().hex[:8]}"

        book = Book(
            id=test_book_id,
            content_hash=f"hash_{uuid4().hex}",
            title="Test Book",
            author="Test Author",
            total_pages=1,
            status="ocr_done"
        )
        test_session.add(book)

        page = Page(
            book_id=test_book_id,
            page_number=1,
            status="ocr_done",
            text="This is a long text that will be chunked. " * 50  # Long enough to chunk
        )
        test_session.add(page)
        await test_session.commit()

        # Chunk the pages
        await service.chunk_ocr_done_pages(limit=10)

        # Verify page status updated
        await test_session.refresh(page)
        assert page.status == "chunked"

        # Verify chunks were created
        from sqlalchemy import select, and_
        stmt = select(Chunk).where(
            and_(Chunk.book_id == test_book_id, Chunk.page_number == 1)
        )
        result = await test_session.execute(stmt)
        chunks = result.scalars().all()

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.text is not None
            assert chunk.embedding is None  # Not embedded yet

        # Cleanup
        for chunk in chunks:
            await test_session.delete(chunk)
        await test_session.delete(page)
        await test_session.delete(book)
        await test_session.commit()


class TestBatchServiceHelpers:
    """Test helper methods in BatchService"""

    def test_custom_id_extraction_direct(self):
        """Test extracting custom_id from direct response"""
        result = {"custom_id": "test_123", "response": {}}

        # This would be called in process_job_results
        custom_id = result.get("custom_id")
        assert custom_id == "test_123"

    def test_custom_id_extraction_nested_metadata(self):
        """Test extracting custom_id from nested metadata"""
        result = {
            "metadata": {"custom_id": "test_456"},
            "response": {}
        }

        custom_id = None
        if "custom_id" in result:
            custom_id = result["custom_id"]
        elif "metadata" in result and "custom_id" in result["metadata"]:
            custom_id = result["metadata"]["custom_id"]

        assert custom_id == "test_456"
