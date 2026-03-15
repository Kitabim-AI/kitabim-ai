import asyncio
from app.db.session import init_db
from scanners.word_index_scanner import run_word_index_scanner
from scanners.spell_check_scanner import run_spell_check_scanner

async def main():
    await init_db()
    ctx = {"redis": None} # Scanners might need redis to enqueue jobs
    # Actually scanners need redis ctx
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.core.config import settings
    r = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    ctx["redis"] = r
    
    print("Running Word Index Scanner manually...")
    await run_word_index_scanner(ctx)
    print("Running Spell Check Scanner manually...")
    await run_spell_check_scanner(ctx)
    await r.close()

if __name__ == "__main__":
    asyncio.run(main())
