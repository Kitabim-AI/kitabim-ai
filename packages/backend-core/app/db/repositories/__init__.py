"""Repository layer for database access with SQLAlchemy"""

from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.books_repository import BooksRepository, get_books_repository
from app.db.repositories.pages_repository import PagesRepository, get_pages_repository
from app.db.repositories.chunks_repository import (
    ChunksRepository,
    get_chunks_repository,
)
from app.db.repositories.users_repository import UsersRepository, get_users_repository
from app.db.repositories.graph_repository import GraphRepository

__all__ = [
    "BaseRepository",
    "BooksRepository",
    "get_books_repository",
    "PagesRepository",
    "get_pages_repository",
    "ChunksRepository",
    "get_chunks_repository",
    "UsersRepository",
    "get_users_repository",
    "GraphRepository",
]
