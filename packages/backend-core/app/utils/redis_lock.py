import logging
import uuid
from typing import List
from redis.asyncio import Redis

from app.utils.observability import log_json

logger = logging.getLogger("app.redis_lock")


class RedisLock:
    """A standard Redis-based distributed lock (Redlock style for single instance)."""

    def __init__(
        self,
        redis_client: Redis,
        name: str,
        timeout: int = 3600,
        prefix: str = "page",
    ):
        """
        Args:
            redis_client: The active Redis client.
            name: Unique name identifying what is locked (e.g. page ID).
            timeout: Lock expiration time in seconds (default 1 hour).
            prefix: Lock namespace prefix (e.g. 'ocr', 'chunking', 'embedding', 'spell_check').
        """
        self.redis = redis_client
        self.name = f"lock:{prefix}:{name}"
        self.timeout = timeout
        self.token = str(uuid.uuid4())

    async def acquire(self) -> bool:
        """Acquire the lock. Returns True if successful, False otherwise."""
        try:
            # px expects timeout in milliseconds
            res = await self.redis.set(
                self.name, self.token, px=self.timeout * 1000, nx=True
            )
            return bool(res)
        except Exception as e:
            log_json(
                logger,
                logging.WARNING,
                "Failed to acquire Redis lock",
                name=self.name,
                error=str(e),
            )
            return False

    async def release(self) -> bool:
        """Release the lock atomically using a Lua script."""
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            eval_func = getattr(self.redis, "eval")
            res = await eval_func(script, 1, self.name, self.token)
            return bool(res)
        except Exception as e:
            log_json(
                logger,
                logging.WARNING,
                "Failed to release Redis lock",
                name=self.name,
                error=str(e),
            )
            return False


class MultiPageLock:
    """A context manager to acquire locks for multiple pages and release them automatically on exit."""

    def __init__(
        self,
        redis_client: Redis,
        page_ids: List[int],
        timeout: int = 3600,
        prefix: str = "page",
    ):
        self.redis = redis_client
        self.page_ids = page_ids
        self.timeout = timeout
        self.prefix = prefix
        self.locks = {}  # page_id -> RedisLock
        self.locked_page_ids = []

    async def __aenter__(self) -> List[int]:
        for pid in self.page_ids:
            lock = RedisLock(
                self.redis, str(pid), timeout=self.timeout, prefix=self.prefix
            )
            if await lock.acquire():
                self.locks[pid] = lock
                self.locked_page_ids.append(pid)
            else:
                log_json(
                    logger,
                    logging.WARNING,
                    "Could not acquire distributed lock for page, page skipped",
                    prefix=self.prefix,
                    page_id=pid,
                )
        return self.locked_page_ids

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Release all locks that were acquired
        for pid in list(self.locks.keys()):
            try:
                await self.locks[pid].release()
            except Exception as e:
                log_json(
                    logger,
                    logging.WARNING,
                    "Exception while releasing lock for page",
                    page_id=pid,
                    error=str(e),
                )
