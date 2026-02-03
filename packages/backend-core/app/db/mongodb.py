import logging
import motor.motor_asyncio
from pymongo.errors import OperationFailure
from app.core.config import settings
from app.utils.observability import log_json


class MongoDB:
    client: motor.motor_asyncio.AsyncIOMotorClient | None = None
    db = None

    async def connect_to_storage(self) -> None:
        logger = logging.getLogger("app.db")
        self.client = motor.motor_asyncio.AsyncIOMotorClient(settings.mongodb_url)
        self.db = self.client[settings.database_name]
        try:
            await self.client.admin.command("ping")
            log_json(logger, logging.INFO, "MongoDB connected", database=settings.database_name)
            await self._ensure_indexes()
        except Exception as exc:
            log_json(logger, logging.ERROR, "MongoDB connection failed", error=str(exc))

    async def close_storage(self) -> None:
        if self.client:
            self.client.close()

    async def _ensure_indexes(self) -> None:
        if self.db is None:
            return
        logger = logging.getLogger("app.db")

        async def safe_create_index(collection, keys, **opts):
            try:
                await collection.create_index(keys, **opts)
            except OperationFailure as exc:
                # Ignore conflicts when an index already exists with different options.
                if getattr(exc, "code", None) in {85, 86}:
                    log_json(logger, logging.WARNING, "Index already exists; skipping", keys=keys, error=str(exc))
                    return
                raise

        books = self.db.books
        await safe_create_index(books, [("contentHash", 1)], unique=True)
        await safe_create_index(books, [("status", 1)])
        await safe_create_index(books, [("uploadDate", -1)])
        await safe_create_index(books, [("tags", 1)])
        await safe_create_index(books, [("categories", 1)])

        jobs = self.db.jobs
        await safe_create_index(jobs, [("jobKey", 1)], unique=True)
        await safe_create_index(jobs, [("status", 1)])

        pages = self.db.pages
        await safe_create_index(pages, [("bookId", 1), ("pageNumber", 1)], unique=True)
        await safe_create_index(pages, [("bookId", 1)])
        await safe_create_index(pages, [("status", 1)])


db_manager = MongoDB()


async def get_db():
    return db_manager.db
