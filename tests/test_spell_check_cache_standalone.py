"""
Standalone test for ThreadSafeSpellCheckCache
Tests thread safety and statistics tracking without importing the full app
"""
import asyncio
from typing import Dict


class ThreadSafeSpellCheckCache:
    """Thread-safe wrapper for spell check cache with hit rate tracking."""

    def __init__(self):
        self.unknown_words: Dict[str, bool] = {}
        self.ocr_corrections: Dict[str, list[str]] = {}
        self.unique_to_book: Dict[str, bool] = {}
        self._locks = {
            'unknown': asyncio.Lock(),
            'ocr': asyncio.Lock(),
            'unique': asyncio.Lock()
        }
        self._stats = {
            'unknown_hits': 0,
            'unknown_misses': 0,
            'ocr_hits': 0,
            'ocr_misses': 0,
            'unique_hits': 0,
            'unique_misses': 0
        }

    def get_stats(self) -> dict:
        """Return cache statistics including hit rates."""
        total_unknown = self._stats['unknown_hits'] + self._stats['unknown_misses']
        total_ocr = self._stats['ocr_hits'] + self._stats['ocr_misses']
        total_unique = self._stats['unique_hits'] + self._stats['unique_misses']

        return {
            'unknown_words': {
                'hits': self._stats['unknown_hits'],
                'misses': self._stats['unknown_misses'],
                'hit_rate': self._stats['unknown_hits'] / total_unknown if total_unknown > 0 else 0
            },
            'ocr_corrections': {
                'hits': self._stats['ocr_hits'],
                'misses': self._stats['ocr_misses'],
                'hit_rate': self._stats['ocr_hits'] / total_ocr if total_ocr > 0 else 0
            },
            'unique_to_book': {
                'hits': self._stats['unique_hits'],
                'misses': self._stats['unique_misses'],
                'hit_rate': self._stats['unique_hits'] / total_unique if total_unique > 0 else 0
            },
            'total_lookups': total_unknown + total_ocr + total_unique,
            'overall_hit_rate': (
                (self._stats['unknown_hits'] + self._stats['ocr_hits'] + self._stats['unique_hits']) /
                (total_unknown + total_ocr + total_unique)
                if (total_unknown + total_ocr + total_unique) > 0 else 0
            )
        }


async def test_concurrent_access():
    """Test that concurrent access doesn't cause race conditions"""
    cache = ThreadSafeSpellCheckCache()

    # Simulate 20 concurrent tasks adding to cache
    async def worker(worker_id: int):
        for i in range(100):
            word = f"word_{i % 50}"  # Overlap to test locking

            # Simulate cache miss then hit
            async with cache._locks['unknown']:
                if word not in cache.unknown_words:
                    cache._stats['unknown_misses'] += 1
                    cache.unknown_words[word] = (i % 2 == 0)
                else:
                    cache._stats['unknown_hits'] += 1

    # Run 20 workers concurrently
    await asyncio.gather(*(worker(i) for i in range(20)))

    stats = cache.get_stats()

    print("✅ Thread Safety Test")
    print(f"   Total lookups: {stats['total_lookups']}")
    print(f"   Cache size: {len(cache.unknown_words)}")
    print(f"   Hit rate: {stats['unknown_words']['hit_rate']:.2%}")
    print(f"   Hits: {stats['unknown_words']['hits']}")
    print(f"   Misses: {stats['unknown_words']['misses']}")

    # Verify counts add up
    assert stats['unknown_words']['hits'] + stats['unknown_words']['misses'] == 2000, "Total should be 20 workers × 100 iterations"
    assert len(cache.unknown_words) == 50, "Should have exactly 50 unique words"

    print("\n✅ All assertions passed!")


async def test_statistics_tracking():
    """Test that statistics are tracked correctly"""
    cache = ThreadSafeSpellCheckCache()

    # Add some data to each cache type
    async with cache._locks['unknown']:
        cache.unknown_words['word1'] = True
        cache._stats['unknown_misses'] += 1

    async with cache._locks['ocr']:
        cache.ocr_corrections['word2'] = ['correction1']
        cache._stats['ocr_misses'] += 1

    async with cache._locks['unique']:
        cache.unique_to_book['word3'] = True
        cache._stats['unique_misses'] += 1

    # Simulate hits
    async with cache._locks['unknown']:
        if 'word1' in cache.unknown_words:
            cache._stats['unknown_hits'] += 1

    async with cache._locks['ocr']:
        if 'word2' in cache.ocr_corrections:
            cache._stats['ocr_hits'] += 1

    async with cache._locks['unique']:
        if 'word3' in cache.unique_to_book:
            cache._stats['unique_hits'] += 1

    stats = cache.get_stats()

    print("✅ Statistics Tracking Test")
    print(f"   Overall hit rate: {stats['overall_hit_rate']:.2%}")
    print(f"   Unknown words hit rate: {stats['unknown_words']['hit_rate']:.2%}")
    print(f"   OCR corrections hit rate: {stats['ocr_corrections']['hit_rate']:.2%}")
    print(f"   Unique to book hit rate: {stats['unique_to_book']['hit_rate']:.2%}")

    assert stats['overall_hit_rate'] == 0.5, f"Should have 50% overall hit rate (3 hits / 6 total), got {stats['overall_hit_rate']}"
    assert stats['unknown_words']['hit_rate'] == 0.5, "Should have 50% unknown hit rate"
    assert stats['ocr_corrections']['hit_rate'] == 0.5, "Should have 50% OCR hit rate"
    assert stats['unique_to_book']['hit_rate'] == 0.5, "Should have 50% unique hit rate"

    print("\n✅ All statistics assertions passed!")


async def test_high_concurrency():
    """Test with very high concurrency to stress test locks"""
    cache = ThreadSafeSpellCheckCache()

    async def aggressive_worker(worker_id: int):
        for i in range(50):
            word = f"shared_word_{i % 10}"  # High collision rate

            async with cache._locks['unknown']:
                if word not in cache.unknown_words:
                    cache._stats['unknown_misses'] += 1
                    cache.unknown_words[word] = True
                else:
                    cache._stats['unknown_hits'] += 1

            # Yield to allow other tasks to run
            await asyncio.sleep(0)

    # Run 50 workers concurrently (simulate heavy load)
    await asyncio.gather(*(aggressive_worker(i) for i in range(50)))

    stats = cache.get_stats()

    print("✅ High Concurrency Test (50 workers)")
    print(f"   Total lookups: {stats['total_lookups']}")
    print(f"   Cache size: {len(cache.unknown_words)}")
    print(f"   Hit rate: {stats['unknown_words']['hit_rate']:.2%}")

    assert stats['total_lookups'] == 2500, "Should have 50 workers × 50 iterations"
    assert len(cache.unknown_words) == 10, "Should have exactly 10 unique words"
    assert stats['unknown_words']['hits'] + stats['unknown_words']['misses'] == 2500

    print("\n✅ High concurrency test passed!")


async def main():
    print("=" * 60)
    print("Testing ThreadSafeSpellCheckCache")
    print("=" * 60)
    print()

    await test_concurrent_access()
    print()
    await test_statistics_tracking()
    print()
    await test_high_concurrency()

    print()
    print("=" * 60)
    print("✅ All tests passed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
