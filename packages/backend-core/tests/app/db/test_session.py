"""
Test SQLAlchemy setup and basic functionality.

Run with: pytest packages/backend-core/tests/test_sqlalchemy_setup.py -v
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models import Base, Book, Page, Chunk, User
from app.db.session import get_database_url
from app.db.repositories import BooksRepository, PagesRepository, ChunksRepository


@pytest.fixture
async def test_engine():
    """Create test database engine"""
    # Use main database for now (TODO: create separate test database)
    database_url = get_database_url()

    engine = create_async_engine(
        database_url,
        echo=True  # Show SQL queries
    )

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Database not available for integration tests: {exc}")

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


@pytest.mark.asyncio
async def test_database_connection(test_engine):
    """Test basic database connection"""
    async with test_engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_database_version(test_engine):
    """Test PostgreSQL version query"""
    async with test_engine.begin() as conn:
        result = await conn.execute(text("SELECT version()"))
        version = result.scalar()
        assert version is not None
        assert "PostgreSQL" in version


@pytest.mark.asyncio
async def test_pgvector_extension(test_engine):
    """Test pgvector extension is installed"""
    async with test_engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            )
        """))
        assert result.scalar() is True


@pytest.mark.asyncio
async def test_books_repository_count(test_session):
    """Test BooksRepository basic count operation"""
    repo = BooksRepository(test_session)

    # This should work even with 0 books
    count = await repo.count()
    assert count >= 0


@pytest.mark.asyncio
async def test_sqlalchemy_models_exist():
    """Test that all SQLAlchemy models are defined"""
    assert Book is not None
    assert Page is not None
    assert Chunk is not None
    assert User is not None

    # Test model table names
    assert Book.__tablename__ == "books"
    assert Page.__tablename__ == "pages"
    assert Chunk.__tablename__ == "chunks"
    assert User.__tablename__ == "users"


@pytest.mark.asyncio
async def test_repositories_instantiate(test_session):
    """Test that repositories can be instantiated"""
    books_repo = BooksRepository(test_session)
    pages_repo = PagesRepository(test_session)
    chunks_repo = ChunksRepository(test_session)

    assert books_repo is not None
    assert pages_repo is not None
    assert chunks_repo is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
