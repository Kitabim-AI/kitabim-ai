import asyncio
from app.db import session as db_session
from app.db.session import init_db
from app.db.repositories.system_configs import SystemConfigsRepository

async def check():
    await init_db()
    async with db_session.async_session_factory() as session:
        repo = SystemConfigsRepository(session)
        val = await repo.get_value("pdf_processing_enabled")
        print(f"pdf_processing_enabled: {val}")

if __name__ == "__main__":
    asyncio.run(check())
