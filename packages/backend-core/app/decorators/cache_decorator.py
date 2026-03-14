from __future__ import annotations
import functools
import hashlib
import json
from typing import Any, Callable, Optional, TypeVar

from app.services.cache_service import cache_service

T = TypeVar("T")

def generate_key_from_args(*args, **kwargs) -> str:
    """Generate a stable hash from function arguments."""
    # Filter out sensitive or non-serializable objects if needed
    # For now, a simple JSON dump of args/kwargs (sorted)
    key_tuple = (args, sorted(kwargs.items()))
    return hashlib.md5(json.dumps(key_tuple, default=str).encode()).hexdigest()

def cached(
    key_prefix: str,
    ttl: Optional[int] = None,
    condition: Optional[Callable[[Any], bool]] = None,
    skip_for_admins: bool = False
):
    """
    Cache decorator for async functions.
    
    Args:
        key_prefix: Cache key prefix
        ttl: Time to live in seconds
        condition: Optional function to check if result should be cached
        skip_for_admins: If True, skips cache if 'current_user' in kwargs is admin
    """
    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Check if we should skip cache for admins
            if skip_for_admins:
                user = kwargs.get("current_user")
                if user and getattr(user, "role", None) == "admin":
                    return await func(*args, **kwargs)

            # Generate cache key
            arg_hash = generate_key_from_args(*args, **kwargs)
            cache_key = f"{key_prefix}:{arg_hash}"

            # Try cache
            cached_result = await cache_service.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute
            result = await func(*args, **kwargs)

            # Check condition
            if condition and not condition(result):
                return result

            # Cache
            await cache_service.set(cache_key, result, ttl)
            return result
            
        return wrapper
    return decorator
