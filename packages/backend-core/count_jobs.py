import asyncio
from app.db.session import async_session_factory
from sqlalchemy import text

async def run():
    async with async_session_factory() as s:
        r = await s.execute(text('SELECT count(*) FROM jobs'))
        print(f'Total jobs: {r.scalar()}')

if __name__ == '__main__':
    asyncio.run(run())
