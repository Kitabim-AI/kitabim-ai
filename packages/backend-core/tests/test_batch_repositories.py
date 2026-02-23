"""
Test Batch Job Repositories.

Run with: pytest packages/backend-core/tests/test_batch_repositories.py -v
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models import BatchJob, BatchRequest
from app.db.repositories.batch_jobs import BatchJobsRepository, BatchRequestsRepository
from app.db.session import get_database_url


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


class TestBatchJobsRepository:
    """Test suite for BatchJobsRepository"""

    @pytest.mark.asyncio
    async def test_create_job(self, test_session):
        """Test creating a batch job"""
        repo = BatchJobsRepository(test_session)

        job = await repo.create_job(
            job_type="ocr",
            request_count=100,
            input_file_uri="files/test-123"
        )

        assert job.id is not None
        assert job.job_type == "ocr"
        assert job.request_count == 100
        assert job.input_file_uri == "files/test-123"
        assert job.status == "created"

        # Cleanup
        await test_session.delete(job)
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_get_by_remote_id(self, test_session):
        """Test getting job by remote ID"""
        repo = BatchJobsRepository(test_session)

        # Create a job
        job = await repo.create_job("embedding", 50)
        remote_id = f"batches/test-{uuid4()}"
        job.remote_job_id = remote_id
        await test_session.commit()

        # Retrieve by remote ID
        found_job = await repo.get_by_remote_id(remote_id)

        assert found_job is not None
        assert found_job.id == job.id
        assert found_job.remote_job_id == remote_id

        # Cleanup
        await test_session.delete(job)
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_get_active_jobs(self, test_session):
        """Test getting active jobs"""
        repo = BatchJobsRepository(test_session)

        # Create test jobs
        job1 = await repo.create_job("ocr", 10)
        job1.status = "submitted"

        job2 = await repo.create_job("embedding", 20)
        job2.status = "completed"  # Not active

        await test_session.commit()

        # Get active jobs
        active_jobs = await repo.get_active_jobs()

        active_ids = [j.id for j in active_jobs]
        assert job1.id in active_ids
        assert job2.id not in active_ids

        # Cleanup
        await test_session.delete(job1)
        await test_session.delete(job2)
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_update_job_status(self, test_session):
        """Test updating job status"""
        repo = BatchJobsRepository(test_session)

        # Create a job
        job = await repo.create_job("ocr", 10)
        job_id = job.id
        await test_session.commit()

        # Update status
        await repo.update_job_status(
            job_id,
            "completed",
            remote_job_id="batches/test-123",
            output_file_uri="files/output-456"
        )
        await test_session.commit()

        # Refresh and check
        await test_session.refresh(job)
        assert job.status == "completed"
        assert job.remote_job_id == "batches/test-123"
        assert job.output_file_uri == "files/output-456"
        assert job.completed_at is not None

        # Cleanup
        await test_session.delete(job)
        await test_session.commit()


class TestBatchRequestsRepository:
    """Test suite for BatchRequestsRepository"""

    @pytest.mark.asyncio
    async def test_create_requests(self, test_session):
        """Test bulk creating batch requests"""
        jobs_repo = BatchJobsRepository(test_session)
        requests_repo = BatchRequestsRepository(test_session)

        # Create a batch job
        job = await jobs_repo.create_job("ocr", 2)
        await test_session.commit()

        # Create requests
        requests_data = [
            {
                "batch_job_id": job.id,
                "book_id": "book123",
                "page_number": 1,
                "request_id": "ocr_book123_1",
                "status": "pending"
            },
            {
                "batch_job_id": job.id,
                "book_id": "book123",
                "page_number": 2,
                "request_id": "ocr_book123_2",
                "status": "pending"
            }
        ]

        await requests_repo.create_requests(requests_data)
        await test_session.commit()

        # Verify
        requests = await requests_repo.find_by_job(job.id)
        assert len(requests) == 2

        # Cleanup
        for req in requests:
            await test_session.delete(req)
        await test_session.delete(job)
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_find_by_job(self, test_session):
        """Test finding requests by job ID"""
        jobs_repo = BatchJobsRepository(test_session)
        requests_repo = BatchRequestsRepository(test_session)

        # Create job and requests
        job = await jobs_repo.create_job("embedding", 1)
        await test_session.commit()

        await requests_repo.create_requests([{
            "batch_job_id": job.id,
            "book_id": "book456",
            "page_number": 10,
            "request_id": "embed_chunk_789",
            "status": "pending"
        }])
        await test_session.commit()

        # Find requests
        requests = await requests_repo.find_by_job(job.id)

        assert len(requests) == 1
        assert requests[0].book_id == "book456"
        assert requests[0].page_number == 10

        # Cleanup
        for req in requests:
            await test_session.delete(req)
        await test_session.delete(job)
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_update_status_by_job(self, test_session):
        """Test updating all request statuses for a job"""
        jobs_repo = BatchJobsRepository(test_session)
        requests_repo = BatchRequestsRepository(test_session)

        # Create job and requests
        job = await jobs_repo.create_job("ocr", 2)
        await test_session.commit()

        await requests_repo.create_requests([
            {
                "batch_job_id": job.id,
                "book_id": "book789",
                "page_number": 1,
                "request_id": "req1",
                "status": "pending"
            },
            {
                "batch_job_id": job.id,
                "book_id": "book789",
                "page_number": 2,
                "request_id": "req2",
                "status": "pending"
            }
        ])
        await test_session.commit()

        # Update all statuses
        count = await requests_repo.update_status_by_job(job.id, "completed")
        await test_session.commit()

        assert count == 2

        # Verify
        requests = await requests_repo.find_by_job(job.id)
        for req in requests:
            assert req.status == "completed"
            await test_session.delete(req)

        # Cleanup
        await test_session.delete(job)
        await test_session.commit()
