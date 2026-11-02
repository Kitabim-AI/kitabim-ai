# Decorators (`app/decorators`)

## Overview
Provides shared async function decorators for caching backend service and repository responses via `cache_service`.

## Interface
- `[cache_decorator.py:T]` — `TypeVar('T')` generic return type variable.
- `[cache_decorator.py:generate_key_from_args]` — `generate_key_from_args(*args, **kwargs) -> str`: Generates an MD5 hex digest from JSON-serialized positional and sorted keyword arguments.
- `[cache_decorator.py:cached]` — `cached(key_prefix: str, ttl: Optional[int] = None, condition: Optional[Callable[[Any], bool]] = None, skip_for_admins: bool = False)`: Async function decorator that caches return values under `{key_prefix}:{arg_hash}`.

## Invariants
- `[cache_decorator.py:generate_key_from_args]` — Computes a deterministic MD5 hex digest (`usedforsecurity=False`) over `json.dumps((args, sorted(kwargs.items())), default=str)`.
- `[cache_decorator.py:cached]` — Constructs cache keys in the format `"{key_prefix}:{arg_hash}"`.
- `[cache_decorator.py:cached]` — When `skip_for_admins=True` and `kwargs.get("current_user")` has `role == "admin"`, bypasses both cache lookup and cache write.
- `[cache_decorator.py:cached]` — Returns the cached value immediately when `await cache_service.get(cache_key)` is not `None`.
- `[cache_decorator.py:cached]` — Skips caching the result when `condition` is provided and `condition(result)` evaluates to falsy.

## Side Effects
- `[cache_decorator.py:cached]` — Reads from Redis/cache backend via `await cache_service.get(cache_key)`.
- `[cache_decorator.py:cached]` — Writes serialized results to Redis/cache backend via `await cache_service.set(cache_key, result, ttl)`.

## Verification
- Run: `pytest packages/backend-core/tests`
