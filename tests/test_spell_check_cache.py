"""
Test script for ThreadSafeSpellCheckCache
Verifies thread safety and statistics tracking
"""
import asyncio
import sys
from pathlib import Path

# Add backend-core to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "backend-core"))

from app.services.spell_check_service import ThreadSafeSpellCheckCache


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

    stats = cache.get_stats()

    print("✅ Statistics Tracking Test")
    print(f"   Overall hit rate: {stats['overall_hit_rate']:.2%}")
    print(f"   Unknown words hit rate: {stats['unknown_words']['hit_rate']:.2%}")
    print(f"   OCR corrections hit rate: {stats['ocr_corrections']['hit_rate']:.2%}")
    print(f"   Unique to book hit rate: {stats['unique_to_book']['hit_rate']:.2%}")

    assert stats['overall_hit_rate'] == 0.5, "Should have 50% overall hit rate (2 hits / 4 total)"
    assert stats['unknown_words']['hit_rate'] == 0.5, "Should have 50% unknown hit rate"
    assert stats['ocr_corrections']['hit_rate'] == 0.5, "Should have 50% OCR hit rate"

    print("\n✅ All statistics assertions passed!")


async def main():
    print("=" * 60)
    print("Testing ThreadSafeSpellCheckCache")
    print("=" * 60)
    print()

    await test_concurrent_access()
    print()
    await test_statistics_tracking()

    print()
    print("=" * 60)
    print("✅ All tests passed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
