import pytest
from app.utils.lru_cache import LocalLRUCache

def test_lru_cache_basic_get_set():
    cache = LocalLRUCache(maxsize=3)
    assert cache.get("a") is None
    
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    
    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert cache.get("c") == 3

def test_lru_cache_eviction():
    cache = LocalLRUCache(maxsize=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    
    # "a" is oldest, "c" is newest.
    # Add "d", which should evict "a"
    cache.set("d", 4)
    
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert cache.get("d") == 4

def test_lru_cache_access_reorders():
    cache = LocalLRUCache(maxsize=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    
    # Access "a", making it the most recently used
    assert cache.get("a") == 1
    
    # "b" is now the oldest (least recently used)
    # Add "d", which should evict "b"
    cache.set("d", 4)
    
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3
    assert cache.get("d") == 4

def test_lru_cache_delete():
    cache = LocalLRUCache(maxsize=3)
    cache.set("a", 1)
    assert cache.delete("a") is True
    assert cache.get("a") is None
    assert cache.delete("a") is False

def test_lru_cache_clear():
    cache = LocalLRUCache(maxsize=3)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
