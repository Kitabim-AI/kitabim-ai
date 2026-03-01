"""Repository layer for database access with SQLAlchemy"""
from app.db.repositories.base import BaseRepository
from app.db.repositories.books import BooksRepository, get_books_repository
from app.db.repositories.pages import PagesRepository, get_pages_repository
from app.db.repositories.chunks import ChunksRepository, get_chunks_repository
from app.db.repositories.users import UsersRepository, get_users_repository

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
]
